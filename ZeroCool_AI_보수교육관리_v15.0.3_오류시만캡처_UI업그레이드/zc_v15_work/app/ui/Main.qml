import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import QtQuick.Dialogs
import "components"

ApplicationWindow {
    id: window
    width: 1536
    height: 1024
    minimumWidth: 980
    minimumHeight: 660
    visible: true
    title: "ZeroCool AI · 서울·경기·인천 교육수료 관리 v15.0.3"
    color: "#f4f7fb"

    readonly property color navy: "#f3f6f9"
    readonly property color blue: "#0f6cbd"
    readonly property color ink: "#10233f"
    readonly property color muted: "#64748b"
    readonly property bool small: width < 1180
    readonly property bool compact: width < 1400 || height < 820
    readonly property real density: small ? .82 : (compact ? .9 : 1)
    readonly property int gutter: small ? 8 : (compact ? 11 : 16)
    readonly property int panelPadding: small ? 9 : (compact ? 11 : 14)

    MessageDialog {
        id: infoDialog
        buttons: MessageDialog.Ok
    }
    Dialog {
        id: toolsDialog
        anchors.centerIn: parent
        width: Math.min(680, window.width - 48)
        height: Math.min(560, window.height - 64)
        modal: true
        title: "기타 기능"
        standardButtons: Dialog.Close
        background: Rectangle {
            radius: 12
            color: "#fbfdff"
            border.color: "#dbe3ec"
        }
        contentItem: ScrollView {
            clip: true
            Column {
                width: parent.width
                spacing: 12
                Text {
                    text: "고급 조회 및 관리 도구"
                    color: window.ink
                    font.pixelSize: 17
                    font.weight: Font.DemiBold
                }
                Text {
                    width: parent.width
                    text: "자주 쓰는 조회는 메인 화면에 유지하고, 보조 작업은 목적별로 모았습니다."
                    color: window.muted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
                Grid {
                    width: parent.width
                    columns: 2
                    columnSpacing: 10
                    rowSpacing: 10
                    Repeater {
                        model: [
                            ["미수료 재조회", "입교예정 제외 대상", "reset", "completion", "incomplete", 0],
                            ["전체 미수료 재조회", "서울·경기·인천 전체", "reset", "completion", "incomplete_all", 0],
                            ["수료일 공란 조회", "수료일이 비어 있는 대상", "search", "completion", "completion_blank", 0],
                            ["결과없음 재조회", "조회 결과가 없는 대상", "search", "completion", "noresult", 0],
                            ["조회오류 재조회", "오류 대상만 다시 조회", "error", "completion", "error", 0],
                            ["입력정보부족 재조회", "정보 보완 대상 확인", "warning", "completion", "input_missing", 0],
                            ["미조회자 조회", "아직 조회하지 않은 대상", "people", "completion", "unqueried", 0],
                            ["3명 테스트", "선택 조건으로 빠른 점검", "play", "completion", "all", 3],
                            ["예약조회 별도 실행", "예약만 독립적으로 조회", "calendar", "reservation", "all", 0],
                            ["결과 폴더 열기", "생성된 Excel 파일 위치", "folder", "special", "results", 0],
                            ["Debug 폴더 열기", "오류 캡처 및 진단 자료", "folder", "special", "debug", 0],
                            ["최근 오류 진단", "로그에서 오류 내용 확인", "info", "special", "error", 0]
                        ]
                        delegate: Button {
                            required property var modelData
                            width: (parent.width - 10) / 2
                            height: 62
                            hoverEnabled: true
                            background: Rectangle {
                                radius: 8
                                color: parent.down ? "#e8f2fc" : parent.hovered ? "#f1f7fd" : "#ffffff"
                                border.width: 1
                                border.color: parent.hovered ? "#8abbea" : "#d9e1ea"
                            }
                            contentItem: Row {
                                leftPadding: 12
                                rightPadding: 10
                                spacing: 10
                                FluentIcon {
                                    name: modelData[2]
                                    tone: "blue"
                                    iconSize: 20
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Column {
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 3
                                    width: parent.width - 52
                                    Text {
                                        text: modelData[0]
                                        color: "#17304f"
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                        width: parent.width
                                    }
                                    Text {
                                        text: modelData[1]
                                        color: "#718096"
                                        font.pixelSize: 9
                                        elide: Text.ElideRight
                                        width: parent.width
                                    }
                                }
                            }
                            onClicked: {
                                if (modelData[3] === "special") {
                                    if (modelData[4] === "results") backend.openResultsFolder()
                                    else if (modelData[4] === "debug") backend.openDebugFolder()
                                    else backend.showLastError()
                                } else {
                                    backend.runTarget(modelData[3], modelData[4], modelData[5])
                                }
                                toolsDialog.close()
                            }
                        }
                    }
                }
            }
        }
    }
    Connections {
        target: backend
        function onToastRequested(title, message) {
            infoDialog.title = title
            infoDialog.text = message
            infoDialog.open()
        }
    }

    Rectangle {
        id: titleBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 44
        color: "#f8fafc"
        border.color: "#e2e7ee"
        border.width: 1
        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.rightMargin: 18
            spacing: 4
            Button {
                text: "⚙  설정"
                flat: true
                font.family: "Segoe UI"
                font.pixelSize: 12
                onClicked: backend.showSettings()
            }
            Button {
                text: "?  도움말"
                flat: true
                font.family: "Segoe UI"
                font.pixelSize: 12
                onClicked: backend.showHelp()
            }
        }
    }

    Rectangle {
        id: sidebar
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: compact ? 72 : 214
        color: window.navy
        border.color: "#dfe5ec"
        border.width: 1
        gradient: Gradient {
            GradientStop { position: 0; color: "#f8fafc" }
            GradientStop { position: 1; color: "#edf3f8" }
        }

        Row {
            x: 18; y: 14; spacing: 10
            Rectangle {
                width: 28; height: 28; radius: 14
                gradient: Gradient {
                    GradientStop { position: 0; color: "#2583e8" }
                    GradientStop { position: 1; color: "#0f5dc0" }
                }
                Text {
                    anchors.centerIn: parent
                    text: "ZC"
                    color: "white"
                    font.pixelSize: 10
                    font.weight: Font.Bold
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "ZeroCool AI Professional"
                visible: !window.compact
                color: "#18314f"
                font.family: "Segoe UI"
                font.pixelSize: compact ? 11 : 12
                font.weight: Font.Medium
            }
        }

        Column {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.topMargin: 76
            spacing: 5
            Text {
                text: "ZeroCool AI"
                visible: !window.compact
                color: "#18314f"
                font.family: "Segoe UI"
                font.pixelSize: 15
                font.weight: Font.DemiBold
                leftPadding: 18
                bottomPadding: 12
            }
            Repeater {
                model: [
                    ["apps", "대시보드"], ["search", "조회 관리"], ["document_text", "결과 관리"],
                    ["people", "대상자 관리"], ["calendar", "예약 관리"], ["chart", "통계 분석"],
                    ["settings", "설정"], ["document", "시스템 로그"]
                ]
                delegate: Button {
                    required property var modelData
                    required property int index
                    width: sidebar.width - (window.compact ? 12 : 20)
                    height: 44
                    x: 10
                    hoverEnabled: true
                    background: Rectangle {
                        radius: 7
                        color: index === 0 ? "#e1effd" : (parent.hovered ? "#e9eef4" : "transparent")
                        border.width: index === 0 ? 1 : 0
                        border.color: "#b8d7f5"
                    }
                    contentItem: Row {
                        spacing: 12
                        leftPadding: window.compact ? 15 : 13
                        FluentIcon {
                            name: modelData[0]; tone: index === 0 ? "blue" : "ink"; iconSize: 18
                            anchors.verticalCenter: parent.verticalCenter
                            opacity: index === 0 ? 1 : .85
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData[1]
                            visible: !window.compact
                            color: index === 0 ? "#0b5cad" : "#30445e"
                            opacity: 1
                            font.family: "Segoe UI"
                            font.pixelSize: 13
                            font.weight: index === 0 ? Font.DemiBold : Font.Normal
                        }
                    }
                    onClicked: {
                        if (index === 0) return
                        if (index === 1) fileButton.forceActiveFocus()
                        else if (index === 2) { backend.setActiveTab(1); backend.openResults() }
                        else if (index === 6) backend.showSettings()
                        else if (index === 7) backend.setActiveTab(0)
                        else backend.toastRequested(modelData[1], "이 기능은 기존 실행 화면에서 계속 사용할 수 있습니다.")
                    }
                }
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: footer.top
            anchors.margins: window.compact ? 8 : 12
            height: window.compact ? 52 : 74
            radius: 9
            color: "#f8fbfe"
            border.color: "#d5dee8"
            Row {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 10
                Rectangle {
                    width: 36; height: 36; radius: 8; color: "#e0edf9"
                    FluentIcon { anchors.centerIn: parent; name: "person"; tone: "blue"; iconSize: 20 }
                }
                Column {
                    visible: !window.compact
                    spacing: 4
                    Text { text: "관리자"; color: "#1d3552"; font.pixelSize: 12; font.weight: Font.DemiBold }
                    Text { text: "admin  •  Online"; color: "#168552"; font.pixelSize: 10 }
                }
            }
        }
        Column {
            id: footer
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.margins: 18
            spacing: 3
            visible: !window.compact
            Text { text: "v15.0 Professional"; color: "#53677f"; font.pixelSize: 10 }
            Text { text: "© 2026 ZeroCool AI"; color: "#7c8ca0"; font.pixelSize: 9 }
        }
    }

    Item {
        id: workspace
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.top: titleBar.bottom
        anchors.bottom: statusBar.top

        Rectangle {
            anchors.fill: parent
            color: "#f6f8fb"
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: window.gutter
            spacing: window.gutter

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: small ? 76 : (compact ? 86 : 98)
                spacing: small ? 9 : 16
                Column {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 310
                    spacing: 6
                    Text {
                        text: "서울 · 경기 · 인천 교육수료 관리"
                        color: window.ink
                        font.family: "Segoe UI"
                        font.pixelSize: small ? 20 : (compact ? 23 : 27)
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: "교육수료 및 예약조회 통합 관리 시스템"
                        color: window.muted
                        font.family: "Segoe UI"
                        font.pixelSize: 12
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.maximumWidth: 760
                    spacing: small ? 6 : 10
                    MetricCard { Layout.fillWidth: true; label: "전체 대상자"; value: String(backend.counts.total || 0); iconName: "people"; tone: "blue" }
                    MetricCard { Layout.fillWidth: true; label: "교육수료"; value: String(backend.counts.completed || 0); iconName: "check_circle"; tone: "green" }
                    MetricCard { Layout.fillWidth: true; label: "입교예정"; value: String(backend.counts.scheduled || 0); iconName: "calendar"; tone: "orange" }
                    MetricCard { Layout.fillWidth: true; label: "미수료"; value: String(backend.counts.incomplete || 0); iconName: "dismiss_circle"; tone: "purple" }
                    MetricCard { Layout.fillWidth: true; label: "조회오류"; value: String(backend.counts.error || 0); iconName: "error"; tone: "red" }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: window.gutter

                Rectangle {
                    Layout.preferredWidth: small ? 272 : (compact ? 308 : 390)
                    Layout.fillHeight: true
                    radius: 10
                    color: "white"
                    border.color: "#e0e6ed"
                    border.width: 1

                    ScrollView {
                        id: conditionScroll
                        anchors.fill: parent
                        anchors.margins: window.panelPadding
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        Column {
                            width: conditionScroll.availableWidth
                            spacing: window.small ? 8 : (window.compact ? 10 : 13)
                            Text {
                                text: "조회 조건 설정"
                                color: window.ink
                                font.family: "Segoe UI"
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                            }
                            Rectangle { width: parent.width; height: 1; color: "#e6ebf1" }
                            Text {
                                text: "1.  파일 및 기관 선택"
                                color: window.blue
                                font.family: "Segoe UI"
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Button {
                                id: fileButton
                                width: parent.width
                                height: 40
                                focusPolicy: Qt.StrongFocus
                                hoverEnabled: true
                                background: Rectangle {
                                    radius: 7
                                    color: parent.hovered ? "#f8fbff" : "#ffffff"
                                    border.width: parent.activeFocus && parent.focusReason === Qt.TabFocusReason ? 2 : 1
                                    border.color: parent.activeFocus && parent.focusReason === Qt.TabFocusReason ? "#111" : "#d6dee9"
                                }
                                contentItem: Row {
                                    leftPadding: 11; rightPadding: 10; spacing: 8
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: parent.width - 36
                                        text: backend.filePath.length ? backend.filePath : "Excel 파일을 선택하세요"
                                        elide: Text.ElideMiddle
                                        color: backend.filePath.length ? "#243750" : "#8490a2"
                                        font.family: "Segoe UI"
                                        font.pixelSize: 11
                                    }
                                    FluentIcon { anchors.verticalCenter: parent.verticalCenter; name: "folder"; tone: "ink"; iconSize: 20 }
                                }
                                onClicked: backend.selectFile()
                            }
                            Row {
                                spacing: 16
                                Repeater {
                                    model: ["서울", "경기", "인천"]
                                    delegate: Button {
                                        required property string modelData
                                        property bool selected: backend.regionChecked(modelData) && backend.statusText.length >= 0
                                        height: 28; width: 64
                                        flat: true
                                        background: Rectangle { color: "transparent" }
                                        contentItem: Row {
                                            spacing: 7
                                            Rectangle {
                                                width: 18; height: 18; radius: 5
                                                color: parent.parent.selected ? "#0f6cbd" : "#f2f5f8"
                                                border.width: parent.parent.selected ? 0 : 1
                                                border.color: "#bdc8d5"
                                                Text { anchors.centerIn: parent; visible: parent.parent.parent.selected; text: "✓"; color: "white"; font.pixelSize: 12; font.weight: Font.Bold }
                                            }
                                            Text { text: modelData; color: "#23364f"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                                        }
                                        onClicked: backend.toggleRegion(modelData)
                                    }
                                }
                            }
                            Button {
                                width: parent.width
                                height: 30
                                property bool selected: backend.backgroundMode
                                flat: true
                                contentItem: Row {
                                    spacing: 8
                                    Rectangle {
                                        width: 18; height: 18; radius: 5
                                        color: parent.parent.selected ? "#0f6cbd" : "#f2f5f8"
                                        border.width: parent.parent.selected ? 0 : 1
                                        border.color: "#bdc8d5"
                                        Text { anchors.centerIn: parent; visible: parent.parent.parent.selected; text: "✓"; color: "white"; font.pixelSize: 12; font.weight: Font.Bold }
                                    }
                                    Text { text: "백그라운드 모드 (작은 창)"; color: "#30445e"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                                }
                                onClicked: backend.setBackgroundMode(!selected)
                            }
                            Rectangle {
                                width: parent.width
                                height: 38
                                radius: 7
                                color: backend.counts.error > 0 ? "#fff0f0" : "#fff6e5"
                                Row {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 7
                                    FluentIcon { name: backend.counts.error > 0 ? "error" : "warning"; tone: backend.counts.error > 0 ? "red" : "orange"; iconSize: 16 }
                                    Text {
                                        text: backend.counts.error > 0
                                              ? "조회오류 " + backend.counts.error + "명 — 재확인이 필요합니다."
                                              : "미수료·입교예정 대상자를 확인해 주세요."
                                        color: backend.counts.error > 0 ? "#b4232c" : "#8a5a00"
                                        font.pixelSize: 10
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                            }
                            Rectangle { width: parent.width; height: 1; color: "#e6ebf1" }
                            Row {
                                width: parent.width
                                Text {
                                    text: "2.  조회 범위"
                                    color: window.blue
                                    font.pixelSize: 13
                                    font.weight: Font.DemiBold
                                }
                            }
                            Grid {
                                width: parent.width
                                columns: 2
                                columnSpacing: 8
                                rowSpacing: 8
                                Repeater {
                                    model: [
                                        ["수료", "#169b55"], ["미수료", "#ef4444"], ["입교예정", "#0f6cbd"],
                                        ["보류", "#f59e0b"], ["제외", "#64748b"], ["조회오류", "#64748b"]
                                    ]
                                    delegate: CheckPill {
                                        required property var modelData
                                        width: (parent.width - 8) / 2
                                        label: modelData[0]
                                        accent: modelData[1]
                                        checkedValue: backend.statusChecked(label) && backend.statusText.length >= 0
                                        onClicked: backend.toggleStatus(label)
                                    }
                                }
                            }
                            Rectangle { width: parent.width; height: 1; color: "#e6ebf1" }
                            Text {
                                text: "3.  조회 항목"
                                color: window.blue
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Grid {
                                width: parent.width
                                columns: window.compact ? 1 : 2
                                columnSpacing: 8
                                rowSpacing: 7
                                CheckPill {
                                    width: window.compact ? parent.width : (parent.width - 8) / 2
                                    label: "수료조회"; subtitle: "실제 수료 여부 확인"
                                    iconName: "board"; accent: "#169b55"
                                    checkedValue: backend.queryChecked(label) && backend.statusText.length >= 0
                                    onClicked: backend.toggleQuery(label)
                                }
                                CheckPill {
                                    width: window.compact ? parent.width : (parent.width - 8) / 2
                                    label: "예약조회"; subtitle: "예약 일정 확인"
                                    iconName: "calendar"; accent: "#0f6cbd"
                                    checkedValue: backend.queryChecked(label) && backend.statusText.length >= 0
                                    onClicked: backend.toggleQuery(label)
                                }
                            }
                            Rectangle {
                                width: parent.width; height: 36; radius: 7; color: "#edfaf3"
                                Row {
                                    anchors.fill: parent
                                    anchors.margins: 9
                                    spacing: 7
                                    FluentIcon { name: "info"; tone: "green"; iconSize: 16 }
                                    Text {
                                        width: parent.width - 24
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: backend.selectionSummary
                                        elide: Text.ElideRight
                                        color: "#168552"; font.pixelSize: 9
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: small ? 200 : (compact ? 218 : 276)
                    Layout.fillHeight: true
                    radius: 10
                    color: "white"
                    border.color: "#e0e6ed"
                    border.width: 1
                    Column {
                        anchors.fill: parent
                        anchors.margins: window.panelPadding
                        spacing: small ? 7 : (compact ? 10 : 16)
                        Rectangle {
                            width: parent.width
                            height: compact ? 104 : 124
                            visible: !window.compact
                            radius: 9
                            gradient: Gradient {
                                GradientStop { position: 0; color: "#edf6ff" }
                                GradientStop { position: 1; color: "#e4f0fc" }
                            }
                            Column {
                                anchors.fill: parent
                                anchors.margins: 16
                                spacing: 9
                                Row {
                                    spacing: 9
                                    FluentIcon { name: "info"; tone: "blue"; iconSize: 22 }
                                    Text { text: "조회 안내"; color: "#1254a0"; font.pixelSize: 14; font.weight: Font.DemiBold }
                                }
                                Text {
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                    text: "선택한 조건에 맞는 대상만 조회하여 빠르고 정확한 결과를 제공합니다."
                                    color: "#50647f"; font.pixelSize: 10; lineHeight: 1.35
                                }
                            }
                        }
                        ActionCard {
                            width: parent.width
                            height: small ? 56 : (compact ? 66 : 100)
                            accent: backend.running ? "#e68a00" : (backend.canResume ? "#1578d4" : "#1671e8")
                            accent2: backend.running ? "#d97706" : (backend.canResume ? "#0f64b4" : "#075ed8")
                            iconName: backend.running ? "pause" : "play"
                            title: backend.running ? (small ? "일시정지" : "조회 일시정지")
                                   : (backend.canResume ? "조회 재개" : (small ? "선택 조회" : "선택 조건으로 조회"))
                            subtitle: compact ? "" : (backend.running ? "현재 작업을 정리한 뒤 멈춥니다"
                                      : (backend.canResume ? "중단된 조건으로 다시 시작합니다" : "선택한 조건으로 조회를 시작합니다"))
                            onClicked: {
                                if (backend.running) backend.stop()
                                else if (backend.canResume) backend.resume()
                                else backend.startSelected()
                            }
                        }
                        ActionCard {
                            width: parent.width
                            height: small ? 56 : (compact ? 66 : 100)
                            accent: "#1aa25b"; accent2: "#13884a"
                            tonal: true
                            iconTone: "green"
                            iconName: "settings"; title: "오늘 업무"
                            subtitle: compact ? "" : "오늘 도래한 업무를 시작합니다"
                            enabled: !backend.running
                            opacity: enabled ? 1 : .55
                            onClicked: backend.startDaily()
                        }
                        ActionCard {
                            width: parent.width
                            height: small ? 56 : (compact ? 66 : 100)
                            accent: "#7550c7"; accent2: "#6038b3"
                            tonal: true
                            iconTone: "purple"
                            iconName: "document_text"; title: small ? "조회 결과" : "조회 결과 보기"
                            subtitle: compact ? "" : "최근 조회 결과를 확인합니다"
                            onClicked: backend.openResults()
                        }
                        ActionCard {
                            width: parent.width
                            height: small ? 52 : (compact ? 60 : 88)
                            quiet: true
                            iconName: "settings"; title: "기타 기능"
                            subtitle: compact ? "" : "설정 및 보조 기능을 관리합니다"
                            onClicked: toolsDialog.open()
                        }
                        Item { width: 1; height: Math.max(0, parent.height - y - stopButton.height) }
                        Button {
                            id: stopButton
                            width: parent.width
                            height: small ? 40 : 46
                            enabled: backend.running || backend.canResume
                            hoverEnabled: true
                            focusPolicy: Qt.StrongFocus
                            background: Rectangle {
                                radius: 8
                                color: !parent.enabled ? "#edf0f4" : (parent.down ? "#b4232c" : parent.hovered ? "#e33d46" : "#d92d36")
                                border.width: parent.activeFocus && parent.focusReason === Qt.TabFocusReason ? 2 : 0
                                border.color: "#111111"
                            }
                            contentItem: Row {
                                spacing: 10
                                anchors.centerIn: parent
                                FluentIcon { name: "stop"; tone: parent.parent.enabled ? "white" : "muted"; iconSize: 20 }
                                Text {
                                    text: backend.running || backend.canResume ? "조회 완전 종료" : "조회 대기"
                                    color: parent.parent.enabled ? "white" : "#8a95a5"
                                    font.pixelSize: 14
                                    font.weight: Font.DemiBold
                                }
                            }
                            onClicked: backend.terminateRun()
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 380
                    radius: 10
                    color: "white"
                    border.color: "#e0e6ed"
                    border.width: 1
                    Column {
                        anchors.fill: parent
                        anchors.margins: window.panelPadding
                        spacing: small ? 7 : 11
                        Row {
                            width: parent.width
                            Text {
                                text: "조회 진행 현황"
                                color: window.ink
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                            }
                            Item { width: parent.width - parent.children[0].width - stateText.width; height: 1 }
                            Text {
                                id: stateText
                                text: backend.running ? "진행 중 · " + backend.elapsedText : backend.statusText
                                color: window.muted
                                font.pixelSize: 10
                                elide: Text.ElideLeft
                                width: Math.min(260, implicitWidth)
                            }
                        }
                        Rectangle {
                            width: parent.width; height: 1; color: "#e6ebf1"
                        }
                        Row {
                            width: parent.width
                            Text {
                                text: backend.running ? "조회 중" : "대기 중"
                                color: "#607086"; font.pixelSize: 10
                            }
                            Item { width: parent.width - parent.children[0].width - percent.width; height: 1 }
                            Text {
                                id: percent
                                text: Math.round(backend.progress * 100) + "%"
                                color: window.blue; font.pixelSize: 11; font.weight: Font.DemiBold
                            }
                        }
                        Rectangle {
                            width: parent.width
                            height: 16
                            radius: 8
                            color: "#e5eaf0"
                            Rectangle {
                                width: Math.max(0, parent.width * backend.progress)
                                height: parent.height
                                radius: 8
                                gradient: Gradient {
                                    GradientStop { position: 0; color: "#0f6cbd" }
                                    GradientStop { position: 1; color: "#1a7bf0" }
                                }
                                Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                            }
                        }
                        Row {
                            spacing: 6
                            Button {
                                height: 38
                                width: 110
                                text: "실시간 로그"
                                checked: backend.activeTab === 0
                                hoverEnabled: true
                                background: Rectangle {
                                    radius: 8
                                    color: parent.checked ? "#ffffff" : "#f1f4f8"
                                    border.width: parent.checked ? 1 : 0
                                    border.color: parent.checked ? "#0f6cbd" : "transparent"
                                }
                                contentItem: Text {
                                    text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                    color: parent.checked ? "#0f6cbd" : "#64748b"; font.pixelSize: parent.checked ? 12 : 11
                                    font.weight: parent.checked ? Font.DemiBold : Font.Normal
                                }
                                onClicked: backend.setActiveTab(0)
                            }
                            Button {
                                height: 34
                                width: 100
                                anchors.verticalCenter: parent.verticalCenter
                                text: "조회 결과"
                                checked: backend.activeTab === 1
                                background: Rectangle {
                                    radius: 8
                                    color: parent.checked ? "#ffffff" : "#f1f4f8"
                                    border.width: parent.checked ? 1 : 0
                                    border.color: parent.checked ? "#0f6cbd" : "transparent"
                                }
                                contentItem: Text {
                                    text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                    color: parent.checked ? "#0f6cbd" : "#64748b"; font.pixelSize: parent.checked ? 12 : 11
                                    font.weight: parent.checked ? Font.DemiBold : Font.Normal
                                }
                                onClicked: backend.setActiveTab(1)
                            }
                        }
                        Rectangle {
                            width: parent.width
                            height: parent.height - y - logActions.height
                            radius: 9
                            color: "#052a4b"
                            border.color: "#0a3a64"
                            border.width: 1
                            TextArea {
                                id: logArea
                                anchors.fill: parent
                                anchors.margins: 10
                                visible: backend.activeTab === 0
                                readOnly: true
                                text: backend.logText
                                color: "#eef7ff"
                                selectionColor: "#1c6fc2"
                                selectedTextColor: "white"
                                wrapMode: TextEdit.NoWrap
                                font.family: "Cascadia Mono"
                                font.pixelSize: 11
                                background: null
                                onTextChanged: cursorPosition = length
                            }
                            Column {
                                visible: backend.activeTab === 1
                                anchors.centerIn: parent
                                spacing: 12
                                FluentIcon { anchors.horizontalCenter: parent.horizontalCenter; name: "document_text"; tone: "blue"; iconSize: 24 }
                                Text { text: "조회 결과 파일"; color: "white"; font.pixelSize: 15; font.weight: Font.DemiBold }
                                Text { text: "최근 생성된 결과를 Excel에서 확인합니다."; color: "#a9c2d8"; font.pixelSize: 11 }
                                Button {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: "결과 열기"
                                    onClicked: backend.openResults()
                                }
                            }
                        }
                        Row {
                            id: logActions
                            width: parent.width
                            height: 40
                            spacing: 8
                            Button { height: 38; text: "로그 저장"; icon.source: "../assets/fluent/png/save_ink_16.png"; onClicked: backend.saveLog() }
                            Button { height: 38; text: "로그 지우기"; icon.source: "../assets/fluent/png/delete_ink_16.png"; onClicked: backend.clearLog() }
                            Item { width: Math.max(0, parent.width - 230); height: 1 }
                            Text { text: "자동 스크롤"; color: "#52647b"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: statusBar
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 48
        color: "#fbfcfe"
        border.color: "#e1e6ed"
        border.width: 1
        Row {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            Text {
                width: parent.width * .55
                text: backend.statusText
                elide: Text.ElideMiddle
                color: "#40536d"
                font.family: "Segoe UI"
                font.pixelSize: 11
            }
            Text {
                width: parent.width * .25
                text: "경과   " + backend.elapsedText
                color: "#40536d"
                font.pixelSize: 11
            }
            Text {
                width: parent.width * .14
                horizontalAlignment: Text.AlignRight
                text: "ZeroCool AI Professional"
                color: "#718096"
                font.pixelSize: 9
            }
            Button {
                width: parent.width * .06
                height: 32
                anchors.verticalCenter: parent.verticalCenter
                hoverEnabled: true
                background: Rectangle {
                    radius: 7
                    color: parent.hovered ? "#fff0f1" : "#fff7f7"
                    border.color: "#f2b9bd"
                }
                contentItem: Text {
                    text: "종료"
                    color: "#d92d36"
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: backend.quitApplication()
            }
        }
    }
}
