import QtQuick
import QtQuick.Effects

Item {
    id: root
    property string label: ""
    property string value: "0"
    property string iconName: "people"
    property string tone: "blue"
    property color accent: "#0f6cbd"
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
            anchors.margins: 12
            spacing: 7
            FluentIcon { name: root.iconName; tone: root.tone; iconSize: 16 }
            Text {
                text: root.label
                color: "#243a58"
                font.family: "Segoe UI"
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
        }
        Text {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.leftMargin: 14
            anchors.bottomMargin: 10
            text: root.value
            color: "#091d3a"
            font.family: "Segoe UI"
            font.pixelSize: 26
            font.weight: Font.DemiBold
        }
        Text {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.rightMargin: 13
            anchors.bottomMargin: 13
            text: "명"
            color: "#68768c"
            font.family: "Segoe UI"
            font.pixelSize: 10
        }
    }
}
