"""Presentation layer for the ZeroCool launcher.

This module owns the dashboard layout and reusable visual controls.  It receives
the application controller and connects existing callbacks without implementing
business rules, file processing, or automation.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk


FONT = "Segoe UI"
FONT_KR = "맑은 고딕"
NAV = "#06264a"
NAV_DEEP = "#041d38"
NAV_ACTIVE = "#0f5cc0"
BLUE = "#0969da"
BLUE_DARK = "#0757b5"
GREEN = "#169b55"
PURPLE = "#673ab7"
ORANGE = "#ff8a00"
RED = "#ef4444"
INK = "#10233f"
MUTED = "#61718a"
BG = "#f4f7fb"
SURFACE = "#ffffff"
WHITE = SURFACE
TEXT = INK
TEXT_MUTED = MUTED
DANGER = RED
BORDER = "#dfe6ef"
PALE_BLUE = "#eef6ff"
PALE_GREEN = "#effaf4"
PALE_WARN = "#fff6e5"


def apply_windows_chrome(app):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        app.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(app.winfo_id())
        light = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(light), ctypes.sizeof(light)
        )
        corner = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner)
        )
    except Exception:
        pass


def apply_dashboard_styles(app):
    style = ttk.Style(app)
    style.theme_use("clam")
    style.configure(".", font=(FONT_KR, 9), background=BG, foreground=INK)
    style.configure("Main.TFrame", background=BG)
    style.configure("White.TFrame", background=SURFACE)
    style.configure(
        "ZC.TButton", font=(FONT_KR, 9, "bold"), padding=(12, 8),
        background="#f5f7fa", foreground=INK, bordercolor=BORDER,
        borderwidth=1, relief="solid",
    )
    style.map(
        "ZC.TButton",
        background=[("pressed", "#e4e9ef"), ("active", "#edf1f5")],
        bordercolor=[("focus", BLUE)],
    )
    style.configure(
        "Primary.TButton", font=(FONT_KR, 9, "bold"), padding=(12, 8),
        background=BLUE, foreground="white", bordercolor=BLUE,
        borderwidth=1,
    )
    style.map(
        "Primary.TButton",
        background=[("pressed", "#0752aa"), ("active", BLUE_DARK)],
    )
    style.configure(
        "Danger.TButton", font=(FONT_KR, 9, "bold"), padding=(12, 8),
        background=RED, foreground="white", bordercolor=RED,
    )
    style.configure(
        "TEntry", fieldbackground=SURFACE, foreground=INK,
        bordercolor="#cfd8e3", lightcolor="#cfd8e3",
        darkcolor="#cfd8e3", padding=(9, 7),
    )
    style.map(
        "TEntry", bordercolor=[("focus", BLUE)],
        lightcolor=[("focus", BLUE)], darkcolor=[("focus", BLUE)],
    )
    style.configure(
        "TCheckbutton", background=SURFACE, foreground=INK,
        font=(FONT_KR, 9), padding=(3, 2), indicatorcolor=SURFACE,
    )
    style.map(
        "TCheckbutton", background=[("active", SURFACE)],
        indicatorcolor=[("selected", BLUE)],
    )
    style.configure(
        "Horizontal.TProgressbar", troughcolor="#dfe4ea", background=BLUE,
        bordercolor="#dfe4ea", lightcolor=BLUE, darkcolor=BLUE, thickness=12,
    )
    style.configure("TNotebook", background=SURFACE, borderwidth=0)
    style.configure(
        "TNotebook.Tab", font=(FONT_KR, 9), padding=(16, 9),
        background="#f1f4f8", foreground=MUTED, borderwidth=0,
    )
    style.map(
        "TNotebook.Tab", background=[("selected", SURFACE)],
        foreground=[("selected", BLUE)],
    )
    style.configure(
        "Treeview", font=(FONT_KR, 9), rowheight=32, background=SURFACE,
        fieldbackground=SURFACE, foreground=INK, bordercolor=BORDER,
    )
    style.map(
        "Treeview", background=[("selected", "#dceeff")],
        foreground=[("selected", INK)],
    )
    style.configure(
        "Treeview.Heading", font=(FONT_KR, 9, "bold"), padding=(8, 8),
        background="#f2f5f9", foreground=INK, bordercolor=BORDER,
    )


def _rounded(canvas, x1, y1, x2, y2, radius, **kwargs):
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class MetricCard(tk.Canvas):
    def __init__(self, master, title, variable, color, icon, command=None):
        super().__init__(master, height=92, bg=BG, highlightthickness=0, bd=0,
                         cursor="hand2" if command else "")
        self.title = title
        self.variable = variable
        self.color = color
        self.icon = icon
        self.command = command
        self.hover = False
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        self.bind("<Button-1>", lambda _e: self.command() if self.command else None)
        variable.trace_add("write", lambda *_a: self.draw())

    def _hover(self, value):
        self.hover = value
        self.draw()

    def draw(self):
        self.delete("all")
        width = max(self.winfo_width(), 120)
        height = max(self.winfo_height(), 88)
        shadow = "#d8e0ea"
        self.create_rectangle(5, 6, width - 2, height - 2, fill=shadow, outline="")
        _rounded(self, 1, 1, width - 5, height - 6, 12,
                 fill="#f8fbff" if self.hover else SURFACE,
                 outline="#b8d6f6" if self.hover else BORDER)
        self.create_oval(16, 14, 36, 34, fill=self.color, outline="")
        self.create_text(26, 24, text=self.icon, fill="white",
                         font=(FONT_KR, 8, "bold"))
        self.create_text(45, 24, text=self.title, anchor="w", fill=INK,
                         font=(FONT_KR, 9, "bold"))
        self.create_text(18, 61, text=self.variable.get(), anchor="w", fill=INK,
                         font=(FONT, 23, "bold"))
        self.create_text(width - 17, 64, text="명", anchor="e", fill=MUTED,
                         font=(FONT_KR, 8))


class ToggleChip(tk.Button):
    def __init__(self, master, text, variable, color, icon="", command=None):
        self.variable = variable
        self.label = text
        self.color = color
        self.icon = icon
        self.user_command = command
        super().__init__(
            master, command=self.toggle, relief="flat", bd=0, cursor="hand2",
            font=(FONT_KR, 9, "bold"), padx=11, pady=9, anchor="w",
        )
        variable.trace_add("write", lambda *_a: self.sync())
        self.sync()

    def toggle(self):
        self.variable.set(not self.variable.get())
        if self.user_command:
            self.user_command()

    def sync(self):
        selected = bool(self.variable.get())
        self.configure(
            text=f"{self.icon}  {self.label}{'     ●' if selected else ''}",
            bg="#f2f7ff" if selected else "#fafbfd",
            fg=self.color if selected else MUTED,
            activebackground="#e8f2ff",
            activeforeground=self.color,
            highlightthickness=1,
            highlightbackground=self.color if selected else BORDER,
            highlightcolor=self.color if selected else BORDER,
        )


class ActionCard(tk.Canvas):
    def __init__(self, master, title, subtitle, icon, command, color, height=108,
                 fg="white", state="normal"):
        super().__init__(master, height=height, bg=SURFACE, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.title = title
        self.subtitle = subtitle
        self.icon = icon
        self.command = command
        self.color = color
        self.fg = fg
        self.state = state
        self.hover = False
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        self.bind("<Button-1>", self._click)

    def _hover(self, value):
        self.hover = value
        self.draw()

    def _click(self, _event):
        if self.state != "disabled" and self.command:
            self.command()

    def configure(self, cnf=None, **kwargs):
        if "state" in kwargs:
            self.state = kwargs.pop("state")
        if "text" in kwargs:
            self.title = kwargs.pop("text")
        super().configure(cnf or {}, **kwargs)
        self.draw()

    config = configure

    def draw(self):
        self.delete("all")
        width = max(self.winfo_width(), 180)
        height = max(self.winfo_height(), 80)
        color = "#c9d2dd" if self.state == "disabled" else self.color
        if self.hover and self.state != "disabled":
            color = _blend(color, "#000000", .10)
        self.create_rectangle(7, 8, width - 2, height - 1, fill="#dbe3ec", outline="")
        _rounded(self, 1, 1, width - 7, height - 7, 10, fill=color, outline="")
        self.create_text(25, 32, text=self.icon, anchor="w", fill=self.fg,
                         font=(FONT_KR, 21, "bold"))
        self.create_text(66, 29, text=self.title, anchor="w", fill=self.fg,
                         font=(FONT_KR, 13, "bold"))
        self.create_text(66, 58, text=self.subtitle, anchor="w", fill=self.fg,
                         font=(FONT_KR, 9))


def _blend(first, second, amount):
    def rgb(value):
        value = value.lstrip("#")
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
    a, b = rgb(first), rgb(second)
    mixed = tuple(round(x + (y - x) * amount) for x, y in zip(a, b))
    return "#" + "".join(f"{value:02x}" for value in mixed)


def _panel(master, padding=14):
    return tk.Frame(
        master, bg=SURFACE, padx=padding, pady=padding,
        highlightbackground=BORDER, highlightthickness=1,
    )


def _section_title(master, title, subtitle=None):
    row = tk.Frame(master, bg=SURFACE)
    row.pack(fill="x", pady=(0, 10))
    tk.Label(row, text=title, bg=SURFACE, fg=INK,
             font=(FONT_KR, 11, "bold")).pack(side="left")
    if subtitle:
        tk.Label(row, text=subtitle, bg=SURFACE, fg=MUTED,
                 font=(FONT_KR, 8)).pack(side="right")
    tk.Frame(master, bg=BORDER, height=1).pack(fill="x", pady=(0, 12))


def _nav_item(master, text, icon, command=None, active=False):
    return tk.Button(
        master, text=f"{icon}   {text}", command=command, anchor="w",
        relief="flat", bd=0, cursor="hand2", padx=16, pady=12,
        bg=NAV_ACTIVE if active else NAV, fg="white" if active else "#d7e5f5",
        activebackground=NAV_ACTIVE, activeforeground="white",
        font=(FONT_KR, 10, "bold" if active else "normal"),
    )


def _build_sidebar(app, master):
    sidebar = tk.Frame(master, width=220, bg=NAV)
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)

    brand = tk.Frame(sidebar, bg=NAV_DEEP, height=78)
    brand.pack(fill="x")
    brand.pack_propagate(False)
    badge = tk.Label(brand, text="ZC", bg=BLUE, fg="white",
                     font=(FONT, 9, "bold"), width=3, height=1)
    badge.pack(side="left", padx=(18, 10), pady=18)
    tk.Label(brand, text="ZeroCool AI Professional", bg=NAV_DEEP, fg="white",
             font=(FONT, 9, "bold")).pack(side="left", pady=25)

    product = tk.Frame(sidebar, bg=NAV)
    product.pack(fill="x", padx=18, pady=(22, 12))
    tk.Label(product, text="ZeroCool AI", bg=NAV, fg="white",
             font=(FONT, 12, "bold")).pack(side="left")
    tk.Label(product, text=" Professional ", bg=NAV_ACTIVE, fg="white",
             font=(FONT, 7)).pack(side="left", padx=8)

    nav = tk.Frame(sidebar, bg=NAV)
    nav.pack(fill="x", padx=12)
    items = [
        ("대시보드", "▦", None, True),
        ("조회 관리", "⌕", app.update_target_preview, False),
        ("결과 관리", "▣", app.open_result, False),
        ("대상자 관리", "♙", app.refresh_file, False),
        ("예약 관리", "▤", app.run_reservation_separate, False),
        ("통계 분석", "▥", app.show_stats, False),
        ("설정", "⚙", app.show_more_actions, False),
        ("시스템 로그", "▧", None, False),
    ]
    for text, icon, command, active in items:
        button = _nav_item(nav, text, icon, command, active)
        button.pack(fill="x", pady=2)

    account = tk.Frame(sidebar, bg=NAV_DEEP, padx=12, pady=12,
                       highlightbackground="#17466f", highlightthickness=1)
    account.pack(side="bottom", fill="x", padx=12, pady=(0, 16))
    tk.Label(account, text="♙", bg="#174d80", fg="white",
             font=(FONT_KR, 16), width=3).pack(side="left", padx=(0, 10))
    account_text = tk.Frame(account, bg=NAV_DEEP)
    account_text.pack(side="left")
    tk.Label(account_text, text="관리자", bg=NAV_DEEP, fg="white",
             font=(FONT_KR, 9, "bold")).pack(anchor="w")
    tk.Label(account_text, text="admin  ● Online", bg=NAV_DEEP, fg="#70d99b",
             font=(FONT, 8)).pack(anchor="w")
    tk.Label(sidebar, text="v15.0 Professional\n© 2026 ZeroCool AI",
             bg=NAV, fg="#b9c9da", justify="left",
             font=(FONT, 8)).pack(side="bottom", anchor="w", padx=20, pady=14)
    return sidebar


def _build_header(app, master):
    header = tk.Frame(master, bg=BG)
    header.pack(fill="x", padx=20, pady=(18, 10))
    title = tk.Frame(header, bg=BG)
    title.pack(side="left")
    tk.Label(title, text="서울 · 경기 · 인천 교육수료 관리", bg=BG, fg=INK,
             font=(FONT_KR, 20, "bold")).pack(anchor="w")
    tk.Label(title, text="교육수료 및 예약조회 통합 관리 시스템", bg=BG, fg=MUTED,
             font=(FONT_KR, 9)).pack(anchor="w", pady=(4, 0))

    metrics = tk.Frame(header, bg=BG)
    metrics.pack(side="right", fill="x", expand=True, padx=(28, 0))
    metric_keys = (
        "전체", "교육수료", "입교예정", "미수료", "보류", "제외",
        "예약확인필요", "정보변경확인", "결과없음", "조회오류",
        "입력정보부족", "미조회",
    )
    for key in metric_keys:
        app.vars.setdefault(key, tk.StringVar(value="0"))
    specs = [
        ("전체 대상자", "전체", BLUE, "Σ"),
        ("교육수료", "교육수료", GREEN, "✓"),
        ("입교예정", "입교예정", ORANGE, "▣"),
        ("미수료", "미수료", PURPLE, "×"),
        ("조회오류", "조회오류", RED, "!"),
    ]
    for index, (title_text, key, color, icon) in enumerate(specs):
        variable = app.vars.setdefault(key, tk.StringVar(value="0"))
        card = MetricCard(
            metrics, title_text, variable, color, icon,
            command=lambda current=key: app.apply_status_filter(current),
        )
        card.grid(row=0, column=index, sticky="nsew", padx=5)
        metrics.columnconfigure(index, weight=1, uniform="metric")


def _build_conditions(app, master):
    panel = _panel(master, 14)
    panel.pack(fill="both", expand=True)
    _section_title(panel, "조회 조건 설정")

    tk.Label(panel, text="1.  파일 및 기관 선택", bg=SURFACE, fg=BLUE,
             font=(FONT_KR, 10, "bold")).pack(anchor="w", pady=(0, 8))
    file_row = tk.Frame(panel, bg=SURFACE)
    file_row.pack(fill="x")
    app.file = tk.StringVar()
    entry = ttk.Entry(file_row, textvariable=app.file, font=(FONT_KR, 9))
    entry.pack(side="left", fill="x", expand=True)
    ttk.Button(file_row, text="찾아보기", style="ZC.TButton",
               command=app.pick).pack(side="left", padx=(6, 0))

    app.seoul = tk.BooleanVar(value=True)
    app.gg = tk.BooleanVar(value=True)
    app.incheon = tk.BooleanVar(value=True)
    app.background_mode = tk.BooleanVar(value=True)
    app.ai_priority = tk.BooleanVar(value=False)
    region = tk.Frame(panel, bg=SURFACE)
    region.pack(fill="x", pady=(10, 4))
    for label, variable in (("서울", app.seoul), ("경기", app.gg), ("인천", app.incheon)):
        ttk.Checkbutton(region, text=label, variable=variable).pack(side="left", padx=(0, 14))
    ttk.Checkbutton(panel, text="백그라운드 모드 (작은 창)",
                    variable=app.background_mode).pack(anchor="w", pady=(3, 8))

    app.alert_var = tk.StringVar(value="미수료·입교예정 대상자를 확인해 주세요.")
    app.alert_bar = tk.Label(panel, textvariable=app.alert_var, bg=PALE_WARN,
                             fg="#885400", font=(FONT_KR, 8), anchor="w",
                             padx=10, pady=9)
    app.alert_bar.pack(fill="x", pady=(2, 12))
    tk.Frame(panel, bg=BORDER, height=1).pack(fill="x", pady=(0, 12))

    range_header = tk.Frame(panel, bg=SURFACE)
    range_header.pack(fill="x", pady=(0, 8))
    tk.Label(range_header, text="2.  조회 범위 (복수 선택 가능)", bg=SURFACE,
             fg=BLUE, font=(FONT_KR, 10, "bold")).pack(side="left")
    tk.Button(range_header, text="전체 선택", command=app.toggle_all_statuses_button,
              bg="#f5f7fa", fg=INK, relief="flat", bd=0, padx=10, pady=5,
              font=(FONT_KR, 8)).pack(side="right")

    status_grid = tk.Frame(panel, bg=SURFACE)
    status_grid.pack(fill="x")
    status_items = [
        ("수료", "completed", GREEN, "●"), ("미수료", "incomplete", RED, "×"),
        ("입교예정", "scheduled", BLUE, "▣"), ("보류", "hold", ORANGE, "◐"),
        ("제외", "excluded", MUTED, "−"), ("조회오류", "error", "#53647b", "△"),
    ]
    for index, (label, key, color, icon) in enumerate(status_items):
        ToggleChip(status_grid, label, app.status_vars[key], color, icon,
                   app.on_status_changed).grid(
            row=index // 2, column=index % 2, sticky="ew", padx=4, pady=4
        )
    status_grid.columnconfigure(0, weight=1)
    status_grid.columnconfigure(1, weight=1)

    tk.Frame(panel, bg=BORDER, height=1).pack(fill="x", pady=12)
    query_header = tk.Frame(panel, bg=SURFACE)
    query_header.pack(fill="x", pady=(0, 8))
    tk.Label(query_header, text="3.  조회 항목 (선택)", bg=SURFACE, fg=BLUE,
             font=(FONT_KR, 10, "bold")).pack(side="left")
    tk.Button(query_header, text="전체 선택", command=app.toggle_all_queries_button,
              bg="#f5f7fa", fg=INK, relief="flat", bd=0, padx=10, pady=5,
              font=(FONT_KR, 8)).pack(side="right")
    query_grid = tk.Frame(panel, bg=SURFACE)
    query_grid.pack(fill="x")
    ToggleChip(query_grid, "수료조회", app.query_vars["completion"], GREEN, "◆",
               app.on_query_changed).grid(row=0, column=0, sticky="ew", padx=4, pady=4)
    ToggleChip(query_grid, "예약조회", app.query_vars["reservation"], BLUE, "▣",
               app.on_query_changed).grid(row=0, column=1, sticky="ew", padx=4, pady=4)
    query_grid.columnconfigure(0, weight=1)
    query_grid.columnconfigure(1, weight=1)

    app.query_note = tk.StringVar(
        value="선택한 항목을 순서대로 조회합니다. (수료조회 → 예약조회)"
    )
    tk.Label(panel, textvariable=app.query_note, bg=PALE_GREEN, fg=GREEN,
             font=(FONT_KR, 8), anchor="w", padx=10, pady=8).pack(
        fill="x", pady=(8, 0)
    )
    app.target_preview = tk.StringVar(value="조회 조건을 계산합니다.")
    tk.Label(panel, textvariable=app.target_preview, bg=PALE_BLUE, fg=INK,
             font=(FONT_KR, 8, "bold"), anchor="w", justify="left",
             padx=10, pady=9, wraplength=360).pack(fill="x", pady=(8, 0))
    return panel


def _build_actions(app, master):
    panel = _panel(master, 16)
    panel.pack(fill="both", expand=True)
    guide = tk.Frame(panel, bg=PALE_BLUE, padx=16, pady=16)
    guide.pack(fill="x", pady=(0, 14))
    tk.Label(guide, text="☼  조회 안내", bg=PALE_BLUE, fg=BLUE,
             font=(FONT_KR, 12, "bold")).pack(anchor="w")
    tk.Label(guide, text="선택한 조건에 맞는 대상만 조회하여\n빠르고 정확한 결과를 제공합니다.",
             bg=PALE_BLUE, fg=MUTED, justify="left",
             font=(FONT_KR, 9)).pack(anchor="w", pady=(12, 0))

    ActionCard(master=panel, title="선택 조건으로 조회",
               subtitle="선택한 조건으로 조회를 시작합니다", icon="⌕",
               command=app.run_filtered, color="#0867e8").pack(fill="x", pady=7)
    ActionCard(master=panel, title="오늘 업무",
               subtitle="오늘 업무를 시작합니다", icon="☼",
               command=app.one_click_run, color=GREEN).pack(fill="x", pady=7)
    ActionCard(master=panel, title="조회 결과 보기",
               subtitle="조회 결과를 확인합니다", icon="▣",
               command=app.open_result, color=PURPLE).pack(fill="x", pady=7)
    ActionCard(master=panel, title="기타 기능",
               subtitle="설정 및 기타 기능을 관리합니다", icon="•••",
               command=app.show_more_actions, color="#edf1f6",
               fg=INK).pack(fill="x", pady=7)

    controls = tk.Frame(panel, bg=SURFACE)
    controls.pack(fill="x", side="bottom", pady=(12, 0))
    app.stop_btn = ActionCard(controls, "조회 중지", "", "■", app.stop, RED,
                              height=44)
    app.stop_btn.pack(fill="x", pady=3)
    app.resume_btn = ActionCard(controls, "중지된 조회 재개", "", "▶",
                                app.resume_run, BLUE, height=44, state="disabled")
    app.resume_btn.pack(side="left", fill="x", expand=True, padx=(0, 3), pady=3)
    app.reset_btn = ActionCard(controls, "새 조회 준비", "", "↺",
                               app.reset_run_state, "#64748b", height=44)
    app.reset_btn.pack(side="left", fill="x", expand=True, padx=(3, 0), pady=3)
    return panel


def _build_monitor(app, master):
    panel = _panel(master, 14)
    panel.pack(fill="both", expand=True)
    app.ptext = tk.StringVar(value="대기 중")
    _section_title(panel, "조회 진행 현황")
    progress_row = tk.Frame(panel, bg=SURFACE)
    progress_row.pack(fill="x")
    tk.Label(progress_row, textvariable=app.ptext, bg=SURFACE, fg=MUTED,
             font=(FONT_KR, 8)).pack(side="left")
    app.progress_percent = tk.StringVar(value="0%")
    tk.Label(progress_row, textvariable=app.progress_percent, bg=SURFACE, fg=BLUE,
             font=(FONT, 10, "bold")).pack(side="right")
    app.pb_var = tk.DoubleVar(value=0)
    app.pb_var.trace_add(
        "write",
        lambda *_a: app.progress_percent.set(f"{int(app.pb_var.get())}%"),
    )
    app.pb = ttk.Progressbar(panel, maximum=100, variable=app.pb_var)
    app.pb.pack(fill="x", pady=(8, 14))

    tabs = ttk.Notebook(panel)
    tabs.pack(fill="both", expand=True)
    log_frame = tk.Frame(tabs, bg=SURFACE)
    result_frame = tk.Frame(tabs, bg=SURFACE)
    tabs.add(log_frame, text="실시간 로그")
    tabs.add(result_frame, text="조회 결과")
    app.main_tabs = tabs

    app.log = tk.Text(
        log_frame, font=("Cascadia Mono", 9), bg="#062442", fg="#eef7ff",
        insertbackground="white", selectbackground=BLUE, wrap="word",
        relief="flat", padx=12, pady=12,
    )
    log_scroll = ttk.Scrollbar(log_frame, orient="vertical",
                               command=app.log.yview)
    app.log.configure(yscrollcommand=log_scroll.set)
    log_scroll.pack(side="right", fill="y")
    app.log.pack(side="left", fill="both", expand=True)

    filter_bar = tk.Frame(result_frame, bg=SURFACE)
    filter_bar.pack(fill="x", pady=(8, 6))
    tk.Label(filter_bar, text="검색", bg=SURFACE, fg=MUTED,
             font=(FONT_KR, 8, "bold")).pack(side="left", padx=(2, 8))
    app.search_var = tk.StringVar()
    search = ttk.Entry(filter_bar, textvariable=app.search_var, width=24)
    search.pack(side="left")
    search.bind("<KeyRelease>", lambda _e: app.render_rows())
    app.filter_label = tk.StringVar(value="전체 명단")
    tk.Label(filter_bar, textvariable=app.filter_label, bg=SURFACE, fg=MUTED,
             font=(FONT_KR, 8)).pack(side="right")

    columns = ("이름", "수료여부", "수료일", "구분", "교육시청일(예정일)", "사이트", "비고")
    app.tree = ttk.Treeview(result_frame, columns=columns, show="headings")
    widths = {
        "이름": 90, "수료여부": 80, "수료일": 150, "구분": 90,
        "교육시청일(예정일)": 120, "사이트": 70, "비고": 130,
    }
    for column in columns:
        app.tree.heading(column, text=column)
        app.tree.column(column, width=widths[column], anchor="center")
    result_scroll = ttk.Scrollbar(result_frame, orient="vertical",
                                  command=app.tree.yview)
    app.tree.configure(yscrollcommand=result_scroll.set)
    result_scroll.pack(side="right", fill="y")
    app.tree.pack(side="left", fill="both", expand=True)

    footer = tk.Frame(panel, bg=SURFACE)
    footer.pack(fill="x", pady=(12, 0))
    ttk.Button(footer, text="로그 저장", style="ZC.TButton",
               command=app.open_folder).pack(side="left")
    ttk.Button(footer, text="로그 지우기", style="ZC.TButton",
               command=lambda: app.log.delete("1.0", "end")).pack(side="left", padx=6)
    ttk.Checkbutton(footer, text="자동 스크롤").pack(side="right")
    return panel


def build_dashboard_ui(app):
    """Build the reference-driven dashboard and attach required widgets to app."""
    app.geometry("1536x920")
    app.minsize(1280, 760)
    app.configure(bg=BG)
    if sys.platform == "win32":
        app.after(50, lambda: app.state("zoomed"))

    shell = tk.Frame(app, bg=BG)
    shell.pack(fill="both", expand=True)
    _build_sidebar(app, shell)

    workspace = tk.Frame(shell, bg=BG)
    workspace.pack(side="left", fill="both", expand=True)
    topbar = tk.Frame(workspace, bg="#f7f9fc", height=42,
                      highlightbackground=BORDER, highlightthickness=1)
    topbar.pack(fill="x")
    topbar.pack_propagate(False)
    tk.Label(topbar, text="⚙  설정      ?  도움말", bg="#f7f9fc", fg=INK,
             font=(FONT_KR, 8)).pack(side="right", padx=20, pady=11)

    app.header_status = tk.StringVar(value="준비")
    _build_header(app, workspace)

    content = tk.Frame(workspace, bg=BG)
    content.pack(fill="both", expand=True, padx=16, pady=(0, 12))
    content.grid_columnconfigure(0, weight=4, uniform="dashboard")
    content.grid_columnconfigure(1, weight=3, uniform="dashboard")
    content.grid_columnconfigure(2, weight=6, uniform="dashboard")
    content.grid_rowconfigure(0, weight=1)

    conditions = tk.Frame(content, bg=BG)
    actions = tk.Frame(content, bg=BG)
    monitor = tk.Frame(content, bg=BG)
    conditions.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    actions.grid(row=0, column=1, sticky="nsew", padx=6)
    monitor.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
    _build_conditions(app, conditions)
    _build_actions(app, actions)
    _build_monitor(app, monitor)

    statusbar = tk.Frame(workspace, bg=SURFACE, height=42,
                         highlightbackground=BORDER, highlightthickness=1)
    statusbar.pack(fill="x", side="bottom")
    statusbar.pack_propagate(False)
    tk.Label(statusbar, textvariable=app.header_status, bg=SURFACE, fg=INK,
             font=(FONT_KR, 8)).pack(side="left", padx=22, pady=12)
    tk.Label(statusbar, text="ZeroCool AI Professional", bg=SURFACE, fg=MUTED,
             font=(FONT, 8)).pack(side="right", padx=22)
