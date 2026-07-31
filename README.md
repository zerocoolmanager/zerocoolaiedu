# zerocoolaiedu
제로쿨 보수교육관리

## Windows 11 Qt UI

일반 사용자는 배포 ZIP을 풀고 루트의 `ZeroCool_AI.exe`만 실행합니다.
Python 설치나 배치 파일 실행은 필요하지 않습니다.

개발 환경에서는 앱 폴더에서 `python qt_launcher.py`로 실행할 수 있습니다.

기존 Tkinter 실행 화면은 그대로 유지되며, Qt 화면은 `qt_launcher.py`와
`ui/*.qml`로 분리되어 있습니다. 실제 조회 엔진은 두 화면 모두 기존
`unified_checker.py`를 사용합니다.
