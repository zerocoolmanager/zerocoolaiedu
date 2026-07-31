import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool selected: false
    width: 78
    height: 25
    padding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    background: Item {
        Rectangle {
            anchors.fill: parent
            anchors.topMargin: 2
            radius: 6
            color: control.selected ? "#0a4f93" : "#cbd3dd"
            opacity: .65
        }
        Rectangle {
            anchors.fill: parent
            anchors.bottomMargin: 2
            radius: 6
            gradient: Gradient {
                GradientStop { position: 0; color: control.selected ? "#2b86dc" : (control.hovered ? "#ffffff" : "#f8fafc") }
                GradientStop { position: 1; color: control.selected ? "#0f6cbd" : "#e7ebf0" }
            }
            border.width: 1
            border.color: control.selected ? "#0c5fa8" : "#c4ccd6"
        }
    }
    contentItem: Text {
        text: (control.selected ? "✓ " : "√ ") + "전체선택"
        color: control.selected ? "white" : "#667488"
        font.family: "Segoe UI"
        font.pixelSize: 10
        font.weight: control.selected ? Font.DemiBold : Font.Normal
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
