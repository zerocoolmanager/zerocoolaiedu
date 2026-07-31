import QtQuick
import QtQuick.Controls
import QtQuick.Effects

Button {
    id: root
    property color accent: "#0f6cbd"
    property color accent2: accent
    property string iconName: "search"
    property string title: ""
    property string subtitle: ""
    property bool quiet: false
    property bool tonal: false
    property string iconTone: tonal ? "blue" : (quiet ? "ink" : "white")
    readonly property bool narrow: width < 220
    implicitHeight: 92
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    scale: down ? 0.985 : (hovered ? 1.008 : 1)
    Behavior on scale { NumberAnimation { duration: 90 } }

    background: Item {
        MultiEffect {
            source: card
            anchors.fill: card
            shadowEnabled: true
            shadowColor: "#24001b3a"
            shadowBlur: 0.5
            shadowVerticalOffset: 3
            visible: !root.down
        }
        Rectangle {
            id: card
            anchors.fill: parent
            radius: 9
            border.width: root.activeFocus && root.focusReason === Qt.TabFocusReason ? 2 : 0
            border.color: "#111111"
            gradient: Gradient {
                GradientStop {
                    position: 0
                    color: root.quiet ? "#f5f7fa"
                         : root.tonal ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, root.hovered ? .16 : .11)
                         : (root.hovered ? Qt.lighter(root.accent, 1.06) : root.accent)
                }
                GradientStop {
                    position: 1
                    color: root.quiet ? "#e9eef4"
                         : root.tonal ? Qt.rgba(root.accent2.r, root.accent2.g, root.accent2.b, root.hovered ? .10 : .06)
                         : root.accent2
                }
            }
        }
        Rectangle {
            visible: root.tonal || root.quiet
            width: 3
            height: parent.height - 20
            radius: 2
            anchors.left: parent.left
            anchors.leftMargin: 5
            anchors.verticalCenter: parent.verticalCenter
            color: root.quiet ? "#8ca0b7" : root.accent
            opacity: .9
        }
    }

    contentItem: Row {
        spacing: root.narrow ? 9 : 14
        leftPadding: root.narrow ? 12 : 19
        rightPadding: root.narrow ? 10 : 16
        Rectangle {
            width: root.narrow ? 30 : 38
            height: width
            radius: root.narrow ? 9 : 11
            anchors.verticalCenter: parent.verticalCenter
            color: root.quiet ? "#ffffff"
                 : root.tonal ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, .12)
                 : "#26ffffff"
            border.width: root.quiet || root.tonal ? 1 : 0
            border.color: root.quiet ? "#d9e1e9" : Qt.rgba(root.accent.r, root.accent.g, root.accent.b, .2)
            FluentIcon {
                anchors.centerIn: parent
                name: root.iconName
                tone: root.iconTone
                iconSize: root.narrow ? 18 : 20
            }
        }
        Column {
            spacing: 6
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - (root.narrow ? 50 : 66)
            Text {
                text: root.title
                color: root.quiet ? "#132a49" : (root.tonal ? root.accent2 : "white")
                font.family: "Segoe UI"
                font.pixelSize: root.narrow ? 13 : 16
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                width: parent.width
            }
            Text {
                text: root.subtitle
                color: root.quiet || root.tonal ? "#647188" : "#eaf4ff"
                font.family: "Segoe UI"
                font.pixelSize: root.narrow ? 9 : 11
                elide: Text.ElideRight
                width: parent.width
            }
        }
    }
}
