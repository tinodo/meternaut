// Validates the Adaptive Card templates of the experience design with the official Microsoft
// libraries and writes one HTML rendering per card (a reference rendering: Teams draws cards with
// its own host settings, so the look differs slightly) and a second at 360 px, a phone width, with
// wrapping buttons (each Teams client wraps or cuts buttons in its own way: the client matrix tests it).
//
// Usage (Node 20 or later; installs three MIT-licensed packages):
//   cd tools/render-cards && npm install
//   node validate-cards.cjs [cardsDir] [outDir]
//
// Defaults: cardsDir = ../../docs/experience/cards, outDir = ./out (not committed).
// Exit code 1 when any card fails to parse, fails validation, or leaves a ${...} placeholder
// unexpanded after the sample data is applied. tools/cardlint.py checks the house rules; this
// script checks that the real library accepts the templates.
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", { pretendToBeVisual: true });
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (!(key in global)) {
    try { global[key] = dom.window[key]; } catch (e) { /* read-only globals */ }
  }
}
global.window = dom.window;
global.document = dom.window.document;
global.navigator = dom.window.navigator;
// jsdom has no innerText; the library sets button titles through it.
Object.defineProperty(dom.window.HTMLElement.prototype, "innerText", {
  get() { return this.textContent; },
  set(value) { this.textContent = value; },
  configurable: true,
});

const AC = require("adaptivecards/dist/adaptivecards.js");
const ACData = require("adaptivecards-templating/dist/adaptivecards-templating.js");
const css = fs.readFileSync(require.resolve("adaptivecards/dist/adaptivecards.css"), "utf8");

AC.AdaptiveCard.onProcessMarkdown = (text, result) => {
  const escaped = String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  result.outputHtml = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\r?\n/g, "<br>");
  result.didProcess = true;
};

const cardsDir = path.resolve(process.argv[2] || path.join(__dirname, "..", "..", "docs", "experience", "cards"));
const outDir = path.resolve(process.argv[3] || path.join(__dirname, "out"));
fs.mkdirSync(outDir, { recursive: true });

const hostConfig = new AC.HostConfig({
  fontFamily: "Segoe UI, Helvetica Neue, sans-serif",
  spacing: { small: 4, default: 8, medium: 12, large: 16, extraLarge: 24, padding: 12 },
  separator: { lineThickness: 1, lineColor: "#E1DFDD" },
  fontSizes: { small: 12, default: 14, medium: 16, large: 18, extraLarge: 22 },
  containerStyles: {
    default: {
      backgroundColor: "#FFFFFF",
      foregroundColors: {
        default: { default: "#242424", subtle: "#616161" },
        accent: { default: "#0F6CBD", subtle: "#0F6CBD" },
        good: { default: "#0E700E", subtle: "#0E700E" },
        warning: { default: "#7A5200", subtle: "#7A5200" },
        attention: { default: "#A4262C", subtle: "#A4262C" },
      },
    },
    emphasis: { backgroundColor: "#EBF3FC", foregroundColors: { default: { default: "#242424", subtle: "#616161" } } },
  },
  actions: { maxActions: 6, spacing: "default", buttonSpacing: 8, showCard: { actionMode: "inline", inlineTopMargin: 8 }, actionsOrientation: "horizontal", actionAlignment: "left" },
});

const page = (body, width = 560) => `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>${css}</style>
<style>body{margin:0;background:#f3f2f1;font-family:Segoe UI,sans-serif}.wrap{width:${width}px;margin:16px;background:#fff;border:1px solid #d1d1d1;border-radius:8px;overflow:hidden}
.ac-pushButton.expandable:after{content:"\\25BE" !important;font-family:"Segoe UI",sans-serif !important}.ac-pushButton.expandable.expanded:after{content:"\\25B4" !important}
${width < 400 ? ".ac-actionSet{flex-wrap:wrap !important;row-gap:8px}.ac-pushButton{flex-shrink:0 !important;white-space:normal !important;max-width:100%}" : ""}</style></head>
<body><div class="wrap">${body}</div></body></html>`;

const manifest = JSON.parse(fs.readFileSync(path.join(cardsDir, "manifest.json"), "utf8"));
let failures = 0;
const report = [];

for (const [id, spec] of Object.entries(manifest.cards)) {
  const template = JSON.parse(fs.readFileSync(path.join(cardsDir, spec.file), "utf8"));
  const data = JSON.parse(fs.readFileSync(path.join(cardsDir, "data", spec.file), "utf8"));
  const expanded = new ACData.Template(template).expand({ $root: data });
  const leftovers = JSON.stringify(expanded).match(/\$\{[^}]*\}/g) || [];

  const card = new AC.AdaptiveCard();
  card.hostConfig = hostConfig;
  const context = new AC.SerializationContext(AC.Versions.v1_5);
  card.parse(expanded, context);
  const parseErrors = [];
  for (let i = 0; i < context.eventCount; i++) parseErrors.push(context.getEventAt(i).message);
  const issues = (card.validateProperties().validationEvents || []).map((e) => e.message);

  const rendered = card.render();
  if (rendered) {
    // The library sets the state of inputs as DOM properties, which a static HTML copy would lose: write them as attributes.
    rendered.querySelectorAll("option").forEach((o) => { if (o.selected) o.setAttribute("selected", ""); else o.removeAttribute("selected"); });
    rendered.querySelectorAll("input[type=checkbox], input[type=radio]").forEach((i) => { if (i.checked) i.setAttribute("checked", ""); else i.removeAttribute("checked"); });
  }
  fs.writeFileSync(path.join(outDir, `${id}-${spec.file.replace(".json", ".html")}`), page(rendered ? rendered.outerHTML : "NO RENDER"));
  // A second rendering at a phone width (360 px), the narrowest case the experience design checks.
  fs.writeFileSync(path.join(outDir, `${id}-${spec.file.replace(".json", "")}-phone.html`), page(rendered ? rendered.outerHTML : "NO RENDER", 360));

  const bad = parseErrors.length + issues.length + leftovers.length + (rendered ? 0 : 1);
  if (bad) failures++;
  report.push({ id, file: spec.file, version: expanded.version, bytes: JSON.stringify(expanded).length, parseErrors, issues, leftovers });
}

fs.writeFileSync(path.join(outDir, "report.json"), JSON.stringify(report, null, 2));
for (const r of report) {
  console.log(r.id.padEnd(4), r.file.padEnd(22), `v${r.version}`, String(r.bytes).padStart(6), "bytes", `parse ${r.parseErrors.length}`, `validate ${r.issues.length}`, `unexpanded ${r.leftovers.length}`);
}
console.log(failures ? `${failures} card(s) with findings` : `all ${report.length} cards parse, validate and expand`);
process.exit(failures ? 1 : 0);
