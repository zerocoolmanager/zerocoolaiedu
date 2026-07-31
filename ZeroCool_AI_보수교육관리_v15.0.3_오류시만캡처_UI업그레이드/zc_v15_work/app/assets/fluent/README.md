# Microsoft Fluent UI System Icons

The icons in this directory come from
[microsoft/fluentui-system-icons](https://github.com/microsoft/fluentui-system-icons)
and are used under the included MIT license.

- `svg/` contains the selected upstream 24px regular icons.
- `png/` contains pre-rendered color and size variants used by Tkinter.
- `build_icons.js` rebuilds the PNG variants with Sharp when the upstream SVG
  selection changes. It is not required to run the launcher.

The application loads only the bundled PNG files and does not require a network
connection or an additional SVG rendering dependency.
