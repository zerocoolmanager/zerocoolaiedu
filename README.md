# zerocoolaiedu
제로쿨 보수교육관리

## Windows 11 Qt UI

앱 폴더에서 의존성을 설치한 뒤 `run_qt.bat`을 실행합니다.

```powershell
python -m pip install -r requirements.txt
.\run_qt.bat
```

기존 Tkinter 실행 화면은 그대로 유지되며, Qt 화면은 `qt_launcher.py`와
`ui/*.qml`로 분리되어 있습니다. 실제 조회 엔진은 두 화면 모두 기존
`unified_checker.py`를 사용합니다.
