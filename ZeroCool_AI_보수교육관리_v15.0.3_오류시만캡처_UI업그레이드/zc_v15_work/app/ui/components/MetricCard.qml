import QtQuick
import QtQuick.Effects

Item {
    id: root
    property string label: ""
    property string value: "0"
    property string iconName: "people"
    property string tone: "blue"
    property color accent: "#0f6cbd"
    readonly property bool narrow: width < 112
    implicitWidth: 128
    implicitHeight: 76

    MultiEffect {
        source: card
        anchors.fill: card
        shadowEnabled: true
        shadowColor: "#18001d3d"
        shadowBlur: 0.45
        shadowVerticalOffset: 2
    }
    Rectangle {
        id: card
        anchors.fill: parent
        radius: 9
        color: "#fbfdff"
        border.color: "#e0e6ee"
        border.width: 1
        Row {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: root.narrow ? 8 : 12
            spacing: root.narrow ? 4 : 7
            FluentIcon { name: root.iconName; tone: root.tone; iconSize: root.narrow ? 14 : 16 }
            Text {
                text: root.label
                color: "#243a58"
                font.family: "Segoe UI"
                font.pixelSize: root.narrow ? 9 : 11
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                width: parent.width - (root.narrow ? 18 : 24)
            }
        }
        Text {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.leftMargin: root.narrow ? 9 : 14
            anchors.bottomMargin: root.narrow ? 9 : 10
            text: root.value
            color: "#091d3a"
            font.family: "Segoe UI"
            font.pixelSize: root.narrow ? 21 : 26
            font.weight: Font.DemiBold
        }
        Text {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.rightMargin: root.narrow ? 8 : 13
            anchors.bottomMargin: root.narrow ? 11 : 13
            text: "명"
            color: "#68768c"
            font.family: "Segoe UI"
            font.pixelSize: root.narrow ? 8 : 10
        }
    }
}
