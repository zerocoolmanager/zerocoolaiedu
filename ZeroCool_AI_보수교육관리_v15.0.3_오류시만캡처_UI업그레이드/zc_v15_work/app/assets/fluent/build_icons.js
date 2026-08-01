// Build bundled PNG variants from the upstream Fluent SVG files.
// This is only needed when updating assets; the launcher has no Node runtime
// dependency and loads the generated images through Tk PhotoImage.
const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const root = __dirname;
const sourceDir = path.join(root, "svg");
const outputDir = path.join(root, "png");
const colors = {
  ink: "#183153",
  white: "#ffffff",
  muted: "#64748b",
  blue: "#0f6cbd",
  green: "#128a4b",
  orange: "#e97800",
  red: "#d13438",
  purple: "#744da9",
};

async function main() {
  fs.mkdirSync(outputDir, { recursive: true });
  const sources = fs.readdirSync(sourceDir).filter((name) => name.endsWith(".svg"));
  for (const source of sources) {
    const stem = path.basename(source, ".svg");
    const original = fs.readFileSync(path.join(sourceDir, source), "utf8");
    for (const [colorName, color] of Object.entries(colors)) {
      const tinted = original.replaceAll('fill="#212121"', `fill="${color}"`);
      for (const size of [16, 20, 24]) {
        await sharp(Buffer.from(tinted))
          .resize(size, size)
          .png()
          .toFile(path.join(outputDir, `${stem}_${colorName}_${size}.png`));
      }
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
