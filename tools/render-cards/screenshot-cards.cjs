// Turns the HTML renderings written by validate-cards.cjs into the PNG pictures in docs/img.
// A headless Microsoft Edge (or Chrome) is driven over the DevTools protocol; each picture is the
// card's own box at twice the pixel density, with a 2 px margin. No npm packages are needed.
//
// Usage (Node 22 or later, which has WebSocket and fetch built in):
//   node validate-cards.cjs                       # writes ./out/*.html
//   node screenshot-cards.cjs [htmlDir] [imgDir] [--all]
//
// Defaults: htmlDir = ./out, imgDir = ../../docs/img. A picture is named experience-card-<name>.png
// after its HTML file (C3-recommendation-phone.html -> experience-card-c3-recommendation-phone.png).
// Only pictures that already exist in imgDir are refreshed; --all creates the others too.
// Set EDGE_PATH (or CHROME_PATH) when the browser is not found.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { pathToFileURL } = require("url");
const { spawn } = require("child_process");

const args = process.argv.slice(2);
const all = args.includes("--all");
const positional = args.filter((a) => !a.startsWith("--"));
const htmlDir = path.resolve(positional[0] || path.join(__dirname, "out"));
const imgDir = path.resolve(positional[1] || path.join(__dirname, "..", "..", "docs", "img"));
const MARGIN = 2;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function findBrowser() {
  const candidates = [
    process.env.EDGE_PATH,
    process.env.CHROME_PATH,
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ].filter(Boolean);
  const found = candidates.find((p) => fs.existsSync(p));
  if (!found) throw new Error("No Edge or Chrome found: set EDGE_PATH to the browser's executable.");
  return found;
}

function connect(url) {
  const ws = new WebSocket(url);
  let nextId = 1;
  const pending = new Map();
  const listeners = [];
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id !== undefined && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(`${msg.error.message} (${msg.error.code})`));
      else resolve(msg.result);
    } else if (msg.method) {
      for (const l of listeners.filter((x) => x.method === msg.method)) {
        listeners.splice(listeners.indexOf(l), 1);
        l.resolve(msg.params);
      }
    }
  };
  const opened = new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = () => reject(new Error("DevTools connection failed"));
  });
  return {
    opened,
    send: (method, params = {}) =>
      new Promise((resolve, reject) => {
        const id = nextId++;
        pending.set(id, { resolve, reject });
        ws.send(JSON.stringify({ id, method, params }));
      }),
    once: (method) => new Promise((resolve) => listeners.push({ method, resolve })),
    close: () => ws.close(),
  };
}

async function main() {
  const files = fs
    .readdirSync(htmlDir)
    .filter((f) => /^C\d+-.*\.html$/.test(f))
    .sort((a, b) => a.localeCompare(b, "en", { numeric: true }));
  if (files.length === 0) throw new Error(`No C*.html files in ${htmlDir}: run validate-cards.cjs first.`);
  fs.mkdirSync(imgDir, { recursive: true });

  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "render-cards-"));
  const browser = spawn(
    findBrowser(),
    ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
      "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"],
    { stdio: "ignore" },
  );
  let written = 0;
  let skipped = 0;
  try {
    const portFile = path.join(profile, "DevToolsActivePort");
    let port;
    for (let i = 0; i < 150 && !port; i++) {
      await sleep(100);
      if (fs.existsSync(portFile)) port = fs.readFileSync(portFile, "utf8").split(/\r?\n/)[0];
    }
    if (!port) throw new Error("The browser did not report a DevTools port.");
    let page;
    for (let i = 0; i < 50 && !page; i++) {
      const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      page = targets.find((t) => t.type === "page");
      if (!page) await sleep(100);
    }
    if (!page) throw new Error("The browser has no page to draw on.");

    const cdp = connect(page.webSocketDebuggerUrl);
    await cdp.opened;
    await cdp.send("Page.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 800, height: 4000, deviceScaleFactor: 2, mobile: false });

    for (const file of files) {
      const name = file.replace(/\.html$/, "");
      const target = path.join(imgDir, `experience-card-${name.toLowerCase()}.png`);
      if (!all && !fs.existsSync(target)) {
        skipped++;
        continue;
      }
      const loaded = cdp.once("Page.loadEventFired");
      await cdp.send("Page.navigate", { url: pathToFileURL(path.join(htmlDir, file)).href });
      await loaded;
      await cdp.send("Runtime.evaluate", { expression: "document.fonts.ready.then(() => true)", awaitPromise: true });
      const { result } = await cdp.send("Runtime.evaluate", {
        expression: "JSON.stringify((() => { const r = document.querySelector('.wrap').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; })())",
        returnByValue: true,
      });
      const box = JSON.parse(result.value);
      const shot = await cdp.send("Page.captureScreenshot", {
        format: "png",
        clip: { x: box.x - MARGIN, y: box.y - MARGIN, width: box.w + 2 * MARGIN, height: box.h + 2 * MARGIN, scale: 1 },
      });
      const png = Buffer.from(shot.data, "base64");
      fs.writeFileSync(target, png);
      written++;
      console.log(`${path.basename(target)}  ${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`);
    }
    cdp.close();
  } finally {
    browser.kill();
    await sleep(500);
    try {
      fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    } catch (e) { /* a leftover temp folder is harmless */ }
  }
  console.log(`${written} picture(s) written, ${skipped} skipped (no picture in ${imgDir}; use --all to create them)`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
