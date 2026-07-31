import QtQuick
import QtQuick.Controls

Button {
    id: root
    property bool checkedValue: false
    property color accent: "#0f6cbd"
    property string iconName: ""
    property string label: ""
    property string subtitle: ""
    readonly property bool narrow: width < 150
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

    contentItem: Item {
        FluentIcon {
            id: leadingIcon
            visible: root.iconName.length > 0
            name: root.iconName
            tone: root.checkedValue ? (root.accent === "#16a060" ? "green" : "blue") : "muted"
            iconSize: 20
            anchors.left: parent.left
            anchors.leftMargin: 12
            anchors.verticalCenter: parent.verticalCenter
        }
        Column {
            anchors.left: root.iconName.length ? leadingIcon.right : parent.left
            anchors.leftMargin: root.iconName.length ? (root.narrow ? 6 : 9) : (root.narrow ? 8 : 12)
            anchors.right: check.left
            anchors.rightMargin: 8
            spacing: 2
            anchors.verticalCenter: parent.verticalCenter
            Text {
                text: root.label
                color: root.checkedValue ? root.accent : "#34445d"
                font.family: "Segoe UI"
                font.pixelSize: root.narrow ? 11 : 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                width: parent.width
            }
            Text {
                visible: root.subtitle.length > 0
                text: root.subtitle
                color: "#758298"
                font.family: "Segoe UI"
                font.pixelSize: root.narrow ? 8 : 10
                elide: Text.ElideRight
                width: parent.width
            }
        }
        Rectangle {
            id: check
            width: root.narrow ? 16 : 18
            height: width
            radius: 5
            anchors.right: parent.right
            anchors.rightMargin: root.narrow ? 7 : 10
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
