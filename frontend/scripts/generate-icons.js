/**
 * Generates PWA icon PNGs from the SVG source.
 * Run once before building: node scripts/generate-icons.js
 *
 * Requires: npm install --save-dev sharp
 */
const path = require("path");
const fs = require("fs");

let sharp;
try {
  sharp = require("sharp");
} catch {
  console.error("Missing dependency. Run: npm install --save-dev sharp");
  process.exit(1);
}

const SRC = path.join(__dirname, "../public/icons/icon.svg");
const OUT_DIR = path.join(__dirname, "../public/icons");
const SIZES = [192, 512];

(async () => {
  const svg = fs.readFileSync(SRC);
  for (const size of SIZES) {
    const out = path.join(OUT_DIR, `icon-${size}.png`);
    await sharp(svg).resize(size, size).png().toFile(out);
    console.log(`✓ ${out}`);
  }

  // Also generate favicon.ico (32x32 PNG works as favicon in most browsers)
  const favicon = path.join(__dirname, "../public/favicon.ico");
  await sharp(svg).resize(32, 32).png().toFile(favicon);
  console.log(`✓ ${favicon}`);

  console.log("\nDone! Icons generated.");
})();
