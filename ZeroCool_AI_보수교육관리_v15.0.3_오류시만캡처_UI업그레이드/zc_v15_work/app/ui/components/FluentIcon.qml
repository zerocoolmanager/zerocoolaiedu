import QtQuick

Image {
    id: root
    property string name: "info"
    property string tone: "ink"
    property int iconSize: 20
    readonly property int sourcePixelSize: iconSize <= 16 ? 16 : (iconSize <= 20 ? 20 : 24)
    source: name.length ? assetBaseUrl + name + "_" + tone + "_" + sourcePixelSize + ".png" : ""
    sourceSize.width: iconSize
    sourceSize.height: iconSize
    width: iconSize
    height: iconSize
    fillMode: Image.PreserveAspectFit
    smooth: true
    mipmap: true
}
