// Dev-only: turns icon.svg into the PNG sizes Chrome needs (16, 32, 48, 128),
// using headless Chrome to draw it with a transparent background.
//   node extension/icons/render-icons.js
// Also writes preview.png (all sizes side by side, enlarged) to check them.

const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { execFileSync } = require("node:child_process");

const DIR = __dirname;
const CHROME = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  path.join(process.env.LOCALAPPDATA || "", "Google/Chrome/Application/chrome.exe"),
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
].find((p) => p && fs.existsSync(p));
if (!CHROME) throw new Error("Chrome not found. Set CHROME_PATH.");

const svg = fs.readFileSync(path.join(DIR, "icon.svg"), "utf8");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "goforit-icons-"));

function render(htmlBody, width, height, out) {
  const page = path.join(tmp, "page.html");
  fs.writeFileSync(page, `<!doctype html><html><head><style>html,body{margin:0;background:transparent}
    img{display:block}</style></head><body>${htmlBody}</body></html>`);
  execFileSync(CHROME, ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--default-background-color=00000000",
    `--window-size=${width},${height}`, `--screenshot=${out}`, `--user-data-dir=${path.join(tmp, "profile")}`,
    `file:///${page.replace(/\\/g, "/")}`], { stdio: "ignore", timeout: 60000 });
}

const toUrl = (text) => `data:image/svg+xml;base64,${Buffer.from(text).toString("base64")}`;
const small = fs.readFileSync(path.join(DIR, "icon16-src.svg"), "utf8"); // simpler design for 16 px
for (const size of [16, 32, 48, 128]) {
  const url = toUrl(size === 16 ? small : svg);
  render(`<img src="${url}" width="${size}" height="${size}">`, size, size, path.join(DIR, `icon${size}.png`));
  console.log(`icon${size}.png`);
}
// Preview: each PNG enlarged 4x without smoothing, on light and dark backgrounds.
const tiles = [16, 32, 48, 128].map((s) => {
  const png = fs.readFileSync(path.join(DIR, `icon${s}.png`)).toString("base64");
  const big = s === 128 ? 128 : s * 4;
  return `<img src="data:image/png;base64,${png}" width="${big}" height="${big}" style="image-rendering:pixelated;margin:8px">`;
}).join("");
render(`<div style="display:flex;align-items:center;background:#fff">${tiles}</div>
        <div style="display:flex;align-items:center;background:#202124">${tiles}</div>`, 560, 380,
       path.join(tmp, "preview.png"));
fs.copyFileSync(path.join(tmp, "preview.png"), process.env.PREVIEW_OUT || path.join(os.tmpdir(), "goforit-icon-preview.png"));
console.log(`preview: ${process.env.PREVIEW_OUT || path.join(os.tmpdir(), "goforit-icon-preview.png")}`);
fs.rmSync(tmp, { recursive: true, force: true });
