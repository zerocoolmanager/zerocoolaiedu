import QtQuick
import QtQuick.Controls

Button {
    id: root
    property bool checkedValue: false
    property color accent: "#0f6cbd"
    property string iconName: ""
    property string label: ""
    property string subtitle: ""
    implicitHeight: subtitle.length ? 58 : 40
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    background: Rectangle {
        radius: 8
        color: root.down ? Qt.darker(root.checkedValue ? "#edf6ff" : "#f6f8fb", 1.03)
                         : root.hovered ? (root.checkedValue ? "#f1f8ff" : "#f7f9fc")
                                        : (root.checkedValue ? "#f7fbff" : "#ffffff")
        border.width: root.activeFocus && root.focusReason === Qt.TabFocusReason ? 2 : 1
        border.color: root.activeFocus && root.focusReason === Qt.TabFocusReason
                      ? "#111111" : (root.checkedValue ? root.accent : "#d7dfe9")
        Behavior on color { ColorAnimation { duration: 100 } }
    }

    contentItem: Row {
        spacing: 9
        leftPadding: 12
        rightPadding: 10
        FluentIcon {
            visible: root.iconName.length > 0
            name: root.iconName
            tone: root.checkedValue ? (root.accent === "#16a060" ? "green" : "blue") : "muted"
            iconSize: 20
            anchors.verticalCenter: parent.verticalCenter
        }
        Column {
            spacing: 2
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(0, parent.width - check.width - (root.iconName.length ? 58 : 38))
            Text {
                text: root.label
                color: root.checkedValue ? root.accent : "#34445d"
                font.family: "Segoe UI"
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            Text {
                visible: root.subtitle.length > 0
                text: root.subtitle
                color: "#758298"
                font.family: "Segoe UI"
                font.pixelSize: 10
                elide: Text.ElideRight
                width: parent.width
            }
        }
        Rectangle {
            id: check
            width: 18; height: 18; radius: 5
            anchors.verticalCenter: parent.verticalCenter
            color: root.checkedValue ? root.accent : "#f4f7fa"
            border.width: root.checkedValue ? 0 : 1
            border.color: "#c5cfdb"
            Text {
                anchors.centerIn: parent
                text: "✓"
                visible: root.checkedValue
                color: "white"
                font.family: "Segoe UI"
                font.pixelSize: 12
                font.weight: Font.Bold
            }
        }
    }
}
