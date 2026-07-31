"""PySide6 entry point for the ZeroCool Windows 11 dashboard.

The automation engine remains in ``unified_checker.py``.  This module only
adapts that engine to Qt properties and signals so the presentation can live
independently in QML.
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
BASE = RESOURCE_BASE
ROOT = Path(sys.executable).resolve().parent if FROZEN else BASE.parent
RESULTS_DIR = ROOT / "results"
DEBUG_DIR = ROOT / "debug"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

_RESULT_SUFFIX_RE = re.compile(
    r"(?:_(?:교육수료조회|3명테스트)"
    r"(?:_\d{8}(?:_\d{6})?)?(?:-\d+)?)$"
)


def canonical_input_stem(path: str | Path) -> str:
    """Return the original workbook stem without generated result suffixes."""
    stem = Path(path).stem
    while True:
        cleaned = _RESULT_SUFFIX_RE.sub("", stem)
        if cleaned == stem:
            return stem
        stem = cleaned


def next_result_path(input_path: str | Path, suffix: str) -> Path:
    """Allocate a stable -1, -2 result name without timestamp accumulation."""
    prefix = f"{canonical_input_stem(input_path)}{suffix}"
    used = set()
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)\.xlsx$", re.IGNORECASE)
    for candidate in RESULTS_DIR.glob(f"{prefix}-*.xlsx"):
        match = pattern.match(candidate.name)
        if match:
            used.add(int(match.group(1)))
    sequence = 1
    while sequence in used or (RESULTS_DIR / f"{prefix}-{sequence}.xlsx").exists():
        sequence += 1
    return RESULTS_DIR / f"{prefix}-{sequence}.xlsx"


class LauncherBridge(QObject):
    changed = Signal()
    toastRequested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._file_path = ""
        self._status = "조회 파일을 선택해 주세요."
        self._log = ""
        self._result_text = "조회가 끝나면 처리 인원과 결과 파일이 여기에 표시됩니다."
        self._error_text = "현재 확인할 오류가 없습니다."
        self._progress = 0.0
        self._running = False
        self._active_tab = 0
        self._elapsed = "00:00:00"
        self._counts = {
            "total": 0, "completed": 0, "scheduled": 0,
            "incomplete": 0, "excluded": 0, "error": 0,
        }
        self._regions = {"서울": True, "경기": True, "인천": True}
        self._statuses = {
            "수료": True, "미수료": True, "입교예정": True,
            "보류": True, "제외": True, "조회오류": True,
        }
        self._queries = {"수료조회": True, "예약조회": True}
        self._background = True
        self._q: queue.Queue[object] = queue.Queue()
        self._proc: subprocess.Popen[str] | None = None
        self._control_file: Path | None = None
        self._started = 0.0
        self._last_output: Path | None = None
        self._pending_followup = False
        self._phase_index = 0
        self._phase_total = 1
        self._phase_name = "수료조회"
        self._pause_requested = False
        self._can_resume = False
        self._last_request: tuple[str, str, int] | None = None
        self._hard_terminated = False
        self._resume_row = -1
        self._last_completed = 0
        self._last_total = 0
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def _get_file_path(self): return self._file_path
    def _get_status(self): return self._status
    def _get_log(self): return self._log
    def _get_result_text(self): return self._result_text
    def _get_error_text(self): return self._error_text
    def _get_progress(self): return self._progress
    def _get_running(self): return self._running
    def _get_active_tab(self): return self._active_tab
    def _get_elapsed(self): return self._elapsed
    def _get_counts(self): return self._counts
    def _get_background(self): return self._background
    def _get_can_resume(self): return self._can_resume
    def _get_region_states(self): return dict(self._regions)
    def _get_status_states(self): return dict(self._statuses)
    def _get_query_states(self): return dict(self._queries)
    def _get_selection_summary(self):
        regions = "·".join(name for name, value in self._regions.items() if value) or "기관 미선택"
        queries = " + ".join(name for name, value in self._queries.items() if value) or "조회 항목 미선택"
        selected_statuses = [name for name, value in self._statuses.items() if value]
        scope = "전체 상태" if len(selected_statuses) == len(self._statuses) else "·".join(selected_statuses) or "상태 미선택"
        browser = "브라우저 완전 숨김" if self._background else "좌측 상단 작은 창"
        return f"{regions}  |  {queries}  |  {scope}  |  {browser}"
    def _get_all_regions_selected(self): return all(self._regions.values())
    def _get_all_statuses_selected(self): return all(self._statuses.values())
    def _get_all_queries_selected(self): return all(self._queries.values())

    filePath = Property(str, _get_file_path, notify=changed)
    statusText = Property(str, _get_status, notify=changed)
    logText = Property(str, _get_log, notify=changed)
    resultText = Property(str, _get_result_text, notify=changed)
    errorText = Property(str, _get_error_text, notify=changed)
    progress = Property(float, _get_progress, notify=changed)
    running = Property(bool, _get_running, notify=changed)
    activeTab = Property(int, _get_active_tab, notify=changed)
    elapsedText = Property(str, _get_elapsed, notify=changed)
    counts = Property("QVariantMap", _get_counts, notify=changed)
    backgroundMode = Property(bool, _get_background, notify=changed)
    canResume = Property(bool, _get_can_resume, notify=changed)
    regionStates = Property("QVariantMap", _get_region_states, notify=changed)
    statusStates = Property("QVariantMap", _get_status_states, notify=changed)
    queryStates = Property("QVariantMap", _get_query_states, notify=changed)
    selectionSummary = Property(str, _get_selection_summary, notify=changed)
    allRegionsSelected = Property(bool, _get_all_regions_selected, notify=changed)
    allStatusesSelected = Property(bool, _get_all_statuses_selected, notify=changed)
    allQueriesSelected = Property(bool, _get_all_queries_selected, notify=changed)

    @Slot()
    def selectFile(self):
        path, _ = QFileDialog.getOpenFileName(
            None, "조회 파일 선택", self._file_path,
            "Excel 파일 (*.xlsx *.xls)",
        )
        if path:
            self._file_path = path
            self._refresh_file()

    @Slot(str, result=bool)
    def regionChecked(self, name):
        return bool(self._regions.get(name, False))

    @Slot(str)
    def toggleRegion(self, name):
        if name in self._regions:
            self._regions[name] = not self._regions[name]
            self.changed.emit()

    @Slot()
    def toggleAllRegions(self):
        target = not all(self._regions.values())
        self._regions = {name: target for name in self._regions}
        self.changed.emit()

    @Slot(str, result=bool)
    def statusChecked(self, name):
        return bool(self._statuses.get(name, False))

    @Slot(str)
    def toggleStatus(self, name):
        if name in self._statuses:
            self._statuses[name] = not self._statuses[name]
            self.changed.emit()

    @Slot()
    def toggleAllStatuses(self):
        target = not all(self._statuses.values())
        self._statuses = {name: target for name in self._statuses}
        self.changed.emit()

    @Slot(str, result=bool)
    def queryChecked(self, name):
        return bool(self._queries.get(name, False))

    @Slot(str)
    def toggleQuery(self, name):
        if name in self._queries:
            self._queries[name] = not self._queries[name]
            self.changed.emit()

    @Slot()
    def toggleAllQueries(self):
        target = not all(self._queries.values())
        self._queries = {name: target for name in self._queries}
        self.changed.emit()

    @Slot(bool)
    def setBackgroundMode(self, enabled):
        self._background = enabled
        self.changed.emit()

    @Slot(int)
    def setActiveTab(self, index):
        self._active_tab = index
        self.changed.emit()

    @Slot()
    def startSelected(self):
        modes = [key for key, selected in self._queries.items() if selected]
        if not modes:
            return self.toastRequested.emit("조회 항목 필요", "수료조회 또는 예약조회를 선택해 주세요.")
        mode = "all" if len(modes) == 2 else ("completion" if modes[0] == "수료조회" else "reservation")
        self._start(mode, "all")

    @Slot()
    def startDaily(self):
        self._start("all", "due")

    @Slot(str, str, int)
    def runTarget(self, mode, target, limit=0):
        self._start(mode or "completion", target or "all", limit)

    @Slot()
    def stop(self):
        if not self._running:
            return
        self._pause_requested = True
        if self._control_file:
            try:
                self._control_file.write_text("STOP", encoding="utf-8")
            except OSError:
                pass
        self._status = "현재 작업을 정리한 뒤 일시정지합니다..."
        self._append_log("Ⅱ 일시정지 요청 · 현재 작업을 안전하게 정리 중")
        self.changed.emit()

    @Slot()
    def resume(self):
        if self._running or not self._can_resume or not self._last_request:
            return
        mode, target, limit = self._last_request
        if limit and self._last_total:
            limit = max(0, self._last_total - self._last_completed)
        self._can_resume = False
        self._append_log("▶ 조회 재개")
        self._start(mode, target, limit, continuation=True, resuming=True)

    @Slot()
    def terminateRun(self):
        self._pending_followup = False
        self._pause_requested = False
        self._can_resume = False
        self._hard_terminated = True
        if self._control_file:
            try:
                self._control_file.write_text("STOP", encoding="utf-8")
            except OSError:
                pass
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        self._running = False
        self._status = "조회 작업을 완전히 종료했습니다."
        self._append_log("■ 조회 완전 종료")
        self.changed.emit()

    @Slot()
    def clearLog(self):
        self._log = ""
        self.changed.emit()

    @Slot()
    def saveLog(self):
        if not self._log.strip():
            return self.toastRequested.emit("로그 없음", "저장할 로그가 없습니다.")
        default = f"zerocool_log_{datetime.now():%Y%m%d_%H%M%S}.txt"
        path, _ = QFileDialog.getSaveFileName(None, "로그 저장", str(BASE / default), "텍스트 (*.txt)")
        if path:
            Path(path).write_text(self._log, encoding="utf-8")
            self.toastRequested.emit("저장 완료", path)

    @Slot()
    def openResults(self):
        target = self._last_output if self._last_output and self._last_output.exists() else RESULTS_DIR
        os.startfile(str(target))

    @Slot()
    def openResultsFolder(self):
        os.startfile(str(RESULTS_DIR))

    @Slot()
    def openDebugFolder(self):
        os.startfile(str(DEBUG_DIR))

    @Slot()
    def showLastError(self):
        self._update_result_views()
        self._active_tab = 2
        self.changed.emit()

    @Slot()
    def quitApplication(self):
        if self._running:
            self.toastRequested.emit("조회 진행 중", "먼저 조회 중지를 눌러 안전하게 작업을 종료해 주세요.")
            return
        QCoreApplication.quit()

    @Slot()
    def showSettings(self):
        self.toastRequested.emit("설정", "백그라운드 모드와 조회 조건은 왼쪽 패널에서 바로 설정할 수 있습니다.")

    @Slot()
    def showHelp(self):
        self.toastRequested.emit(
            "도움말",
            "Excel 파일과 기관·조회 항목을 선택한 뒤 ‘선택 조건으로 조회’를 누르세요. "
            "진행 중에는 안전 중지 버튼으로 현재 작업을 정리할 수 있습니다.",
        )

    def _refresh_file(self):
        try:
            from unified_checker import (
                exclusion_reason, normalize_manual_result_rows, people_from_df,
                read_input, row_result_state,
            )
            _, _, df = read_input(Path(self._file_path))
            normalize_manual_result_rows(df)
            counts = {
                k: 0 for k in
                ("total", "completed", "scheduled", "incomplete", "excluded", "error")
            }
            people = people_from_df(df)
            counts["total"] = len(people)
            for person in people:
                row = df.loc[person.row]
                key, _, category = row_result_state(row)
                exclusion_reason(row)
                if key == "교육수료":
                    counts["completed"] += 1
                elif key == "입교예정":
                    counts["scheduled"] += 1
                elif key == "미수료":
                    counts["incomplete"] += 1
                elif key == "제외":
                    counts["excluded"] += 1
                if key == "조회오류" or category == "조회오류":
                    counts["error"] += 1
            self._counts = counts
            self._status = f"선택됨 · {Path(self._file_path).name} · 전체 {counts['total']}명"
        except Exception as exc:
            self._status = "파일을 분석하지 못했습니다."
            self.toastRequested.emit("파일 분석 오류", str(exc))
        self.changed.emit()

    def _start(self, mode: str, target: str, limit: int = 0, continuation: bool = False, resuming: bool = False):
        if self._running:
            return self.toastRequested.emit("실행 중", "현재 조회가 진행 중입니다.")
        if not self._file_path or not Path(self._file_path).exists():
            return self.toastRequested.emit("파일 필요", "유효한 Excel 신청 양식을 선택해 주세요.")
        regions = [name for name, selected in self._regions.items() if selected]
        if not regions:
            return self.toastRequested.emit("기관 필요", "조회할 기관을 한 곳 이상 선택해 주세요.")

        if mode == "all" and not resuming:
            # Keep the same safety rule as launcher_v3: completion and
            # reservation are separate processes, never mixed in one run.
            self._pending_followup = True
            self._phase_index = 0
            self._phase_total = 2
            mode = "completion"
        elif not continuation and not resuming:
            self._phase_index = 0
            self._phase_total = 1
        self._phase_name = "예약조회" if mode == "reservation" else "수료조회"
        self._last_request = (mode, target, limit)
        if not resuming:
            self._resume_row = -1
            self._last_completed = 0
            self._last_total = 0
        self._pause_requested = False
        self._can_resume = False
        self._hard_terminated = False
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "_3명테스트" if limit else "_교육수료조회"
        if not resuming:
            self._last_output = next_result_path(self._file_path, suffix)
        elif self._last_output is None:
            self._last_output = next_result_path(self._file_path, suffix)
        self._control_file = Path(os.environ.get("TEMP", str(BASE))) / f"zerocool_qt_stop_{os.getpid()}_{stamp}.txt"
        self._control_file.unlink(missing_ok=True)
        if FROZEN:
            cmd = [
                sys.executable, "--worker", self._file_path,
            ]
        else:
            cmd = [
                sys.executable, str(BASE / "unified_checker.py"), self._file_path,
            ]
        cmd += [
            "--regions", ",".join(regions), "--mode", mode, "--target", target,
            "--browser-mode", "hidden" if self._background else "background",
            "--output", str(self._last_output), "--control-file", str(self._control_file),
        ]
        if limit:
            cmd += ["--limit", str(limit)]
        if resuming and self._resume_row >= 0:
            cmd += ["--resume-row", str(self._resume_row)]
        status_keys = {
            "수료": "completed", "미수료": "incomplete", "입교예정": "scheduled",
            "보류": "hold", "제외": "excluded", "조회오류": "error",
        }
        selected_statuses = [
            status_keys[name] for name, selected in self._statuses.items() if selected
        ]
        if selected_statuses and len(selected_statuses) != len(self._statuses):
            cmd += ["--status-filter", ",".join(selected_statuses)]
        if not continuation and not resuming:
            self._log = ""
        self._result_text = "조회 중입니다. 완료되면 결과 요약과 파일 경로가 표시됩니다."
        self._error_text = "조회 중 발견된 오류를 자동으로 모으고 있습니다."
        self._active_tab = 0
        self._progress = self._phase_index / self._phase_total
        self._running = True
        if not continuation and not resuming:
            self._started = time.time()
        self._status = "조회 준비 중..."
        self._append_log(f"● 조회 시작 · {' → '.join(regions)}")
        self._append_log(f"● 조회 항목 · {mode} · 대상 {target}")
        self.changed.emit()

        def worker():
            env = os.environ.copy()
            env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
            try:
                self._proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", env=env, cwd=str(BASE),
                )
                assert self._proc.stdout is not None
                for line in self._proc.stdout:
                    self._q.put(line.rstrip())
                self._q.put(("DONE", self._proc.wait()))
            except Exception as exc:
                self._q.put(f"ERROR|프로그램 실행|{type(exc).__name__}|{exc}")
                self._q.put(("DONE", 1))
            finally:
                self._proc = None

        threading.Thread(target=worker, daemon=True).start()

    def _append_log(self, text: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        self._log += ("" if not self._log else "\n") + f"{stamp}   {text}"

    def _update_result_views(self):
        c = self._counts
        output = str(self._last_output) if self._last_output else "아직 생성된 결과 파일이 없습니다."
        self._result_text = (
            f"전체 대상  {c['total']}명\n"
            f"수료  {c['completed']}명   ·   입교예정  {c['scheduled']}명\n"
            f"미수료  {c['incomplete']}명   ·   제외  {c['excluded']}명   ·   조회오류  {c['error']}명\n\n"
            f"최근 결과 파일\n{output}"
        )
        errors = [
            line for line in self._log.splitlines()
            if "ERROR|" in line or "조회오류" in line or "실패" in line
        ]
        self._error_text = (
            "\n".join(errors[-80:])
            if errors else
            "현재 확인할 오류가 없습니다.\n오류가 생기면 대상자·기관·원인이 이 화면에 모입니다."
        )

    @Slot()
    def _poll(self):
        dirty = False
        if self._running:
            self._elapsed = time.strftime("%H:%M:%S", time.gmtime(max(0, time.time() - self._started)))
            dirty = True
        while True:
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            dirty = True
            if isinstance(item, tuple) and item[0] == "DONE":
                if self._hard_terminated:
                    self._hard_terminated = False
                    self._running = False
                    continue
                code = int(item[1])
                self._running = False
                paused = self._pause_requested
                self._can_resume = paused
                self._pause_requested = False
                if paused:
                    if self._last_output and self._last_output.exists():
                        self._file_path = str(self._last_output)
                        self._refresh_file()
                    self._status = "조회가 일시정지되었습니다. 재개할 수 있습니다."
                    self._append_log("Ⅱ 조회 일시정지 · 파란색 ‘조회 재개’ 버튼을 누르세요.")
                    self._update_result_views()
                    self._active_tab = 0
                    continue
                if code == 0:
                    self._progress = (self._phase_index + 1) / self._phase_total
                self._status = (
                    "조회가 완료되었습니다." if code == 0 else
                    "조회가 중지되었거나 오류가 발생했습니다."
                )
                self._append_log(
                    "✓ 조회 완료" if code == 0 else "■ 조회 종료"
                )
                if code == 0:
                    if self._last_output and self._last_output.exists():
                        # 다음 단계는 앞 단계가 기록한 결과 파일을 이어서 사용한다.
                        self._file_path = str(self._last_output)
                    self._refresh_file()
                    if self._pending_followup:
                        self._pending_followup = False
                        self._phase_index = 1
                        self._append_log("● 수료조회 완료 · 예약조회를 별도 프로세스로 시작합니다.")
                        QTimer.singleShot(
                            250, lambda: self._start("reservation", "all", continuation=True)
                        )
                    else:
                        self._update_result_views()
                        self._active_tab = 2 if self._counts["error"] else 1
                else:
                    self._pending_followup = False
                    self._update_result_views()
                    self._active_tab = 2
            else:
                line = str(item)
                self._append_log(line)
                if line.startswith("PROGRESS|"):
                    try:
                        _, current, total, *_ = line.split("|")
                        current_value, total_value = int(current), max(1, int(total))
                        self._last_completed = max(0, current_value - 1)
                        self._last_total = total_value
                        phase_progress = min(1.0, max(0.0, current_value / total_value))
                        self._progress = (
                            self._phase_index + phase_progress
                        ) / self._phase_total
                        self._status = (
                            f"{self._phase_name} 진행 중 · "
                            f"{current_value}/{total_value}명"
                        )
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("CHECKPOINT|"):
                    try:
                        parts = line.split("|")
                        self._last_completed = int(parts[1])
                        self._last_total = int(parts[2])
                        if len(parts) >= 5:
                            self._resume_row = int(parts[3])
                    except (ValueError, IndexError):
                        pass
                elif "%" in line:
                    for token in line.replace("%", " %").split():
                        if token.isdigit():
                            value = int(token)
                            if 0 <= value <= 100:
                                self._progress = value / 100
                if not line.startswith("PROGRESS|"):
                    self._status = f"{self._phase_name} 진행 중..."
        if dirty:
            self.changed.emit()


def main() -> int:
    if FROZEN and len(sys.argv) > 1 and sys.argv[1] == "--worker":
        # Reuse the packaged runtime for the automation worker.  The end user
        # sees one executable while the UI and Selenium process stay isolated.
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        from unified_checker import main as worker_main
        worker_main()
        return 0
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QApplication(sys.argv)
    app.setApplicationName("ZeroCool AI Professional")
    app.setOrganizationName("ZeroCool AI")
    bridge = LauncherBridge()
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        bridge._file_path = str(Path(sys.argv[1]).resolve())
        bridge._refresh_file()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", bridge)
    asset_url = QUrl.fromLocalFile(str(RESOURCE_BASE / "assets" / "fluent" / "png") + os.sep).toString()
    engine.rootContext().setContextProperty("assetBaseUrl", asset_url)
    engine.load(QUrl.fromLocalFile(str(RESOURCE_BASE / "ui" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    if sys.platform == "win32":
        def apply_windows_chrome():
            try:
                import ctypes
                root = engine.rootObjects()[0]
                hwnd = int(root.winId())
                corner = ctypes.c_int(2)   # DWMWCP_ROUND
                backdrop = ctypes.c_int(2) # DWMSBT_MAINWINDOW (Mica)
                dark = ctypes.c_int(0)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), 4)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), 4)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
            except Exception:
                pass
        QTimer.singleShot(0, apply_windows_chrome)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
