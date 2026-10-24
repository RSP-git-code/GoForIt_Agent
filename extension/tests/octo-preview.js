// Dev-only: screenshots the Octo side panel (with a sample job description checked) to octo-preview.png.
//   node extension/tests/octo-preview.js [output.png]
// Needs the backend running. Reuses the harness's tiny static server + /api proxy.
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");
const http = require("node:http");
const { execFile } = require("node:child_process");

const ROOT = path.join(__dirname, "..", "..");
const OUT = process.argv[2] || path.join(os.tmpdir(), "octo-preview.png");
const CHROME = ["C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  path.join(process.env.LOCALAPPDATA || "", "Google/Chrome/Application/chrome.exe"), process.env.CHROME_PATH].find((p) => p && fs.existsSync(p));
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".css": "text/css", ".png": "image/png" };

const server = http.createServer((req, res) => {
  if (req.url.startsWith("/api/")) {
    const proxy = http.request(new URL(req.url.slice(4), "http://127.0.0.1:8000"),
      { method: req.method, headers: { "Content-Type": "application/json" } }, (up) => { res.writeHead(up.statusCode, { "Content-Type": "application/json" }); up.pipe(res); });
    proxy.on("error", () => res.writeHead(502).end());
    return req.pipe(proxy);
  }
  const file = path.normalize(path.join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname)));
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return res.writeHead(404).end();
  res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});
server.listen(0, "127.0.0.1", () => {
  const port = server.address().port;
  const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "octo-"));
  // execFile (not execFileSync): Chrome loads pages from this same process's server,
  // so Node must keep running while Chrome works.
  execFile(CHROME, ["--headless=new", "--disable-gpu", "--hide-scrollbars", `--user-data-dir=${profileDir}`,
    process.env.OCTO_SIZE ? `--window-size=${process.env.OCTO_SIZE}` : "--window-size=520,1700", "--virtual-time-budget=20000", `--screenshot=${OUT}`,
    `http://127.0.0.1:${port}/extension/tests/octo-preview.html?${process.env.OCTO_QUERY || "run=1"}`], { timeout: 90000 }, (err) => {
    console.log(err ? `failed: ${err.message}` : `screenshot: ${OUT}`);
    server.close();
    fs.rmSync(profileDir, { recursive: true, force: true });
  });
});
