import { readFileSync } from "node:fs";
import { createContext, runInContext } from "node:vm";

function extractFunctions(source, names) {
  let out = "";
  for (const name of names) {
    const start = source.indexOf("function " + name + "(");
    if (start < 0) throw new Error("missing " + name);
    let i = source.indexOf("{", start);
    let depth = 0;
    for (; i < source.length; i++) {
      if (source[i] === "{") depth += 1;
      else if (source[i] === "}") {
        depth -= 1;
        if (depth === 0) {
          out += source.slice(start, i + 1) + "\n";
          break;
        }
      }
    }
  }
  return out;
}

function loadLab(search) {
  const hrefBox = { value: "http://127.0.0.1/lab" + search };
  function el() {
    const node = {
      hidden: true,
      textContent: "",
      innerHTML: "",
      value: "PA",
      className: "",
      style: {},
      dataset: {},
      classList: { toggle() {}, add() {}, remove() {} },
      setAttribute() {},
      getAttribute() { return null; },
      addEventListener() {},
      removeEventListener() {},
      appendChild() {},
      querySelectorAll() { return []; },
      querySelector() { return null; },
      focus() {},
      click() {},
      scrollIntoView() {},
    };
    return node;
  }
  const document = {
    getElementById() { return el(); },
    querySelectorAll() { return []; },
    querySelector() { return el(); },
    addEventListener() {},
    createElement() { return el(); },
    createTextNode(text) { return { textContent: String(text) }; },
    body: el(),
  };
  const sandbox = {
    window: {},
    document,
    location: { search, hash: "", href: hrefBox.value },
    history: { replaceState() {} },
    fetch() { return Promise.reject(new Error("offline")); },
    localStorage: { getItem() { return "1"; }, setItem() {} },
    URLSearchParams,
    Set,
    Object,
    Number,
    Math,
    Promise,
    performance: { now() { return 0; } },
    requestAnimationFrame() {},
    console,
    setTimeout,
    clearTimeout,
    isFinite,
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.window.matchMedia = () => ({ matches: true });
  createContext(sandbox);
  const source = readFileSync(new URL("../../src/web/static/lab.js", import.meta.url), "utf8");
  runInContext(source, sandbox);
  return sandbox.StateframeLab;
}

const unknown = loadLab("?st=PA&on=not_a_reform&county=42001");
const unknownWhy = unknown.whyRequest();
if (unknownWhy.scenario !== "selection") throw new Error("scenario " + unknownWhy.scenario);
if (unknownWhy.reforms.join(",") !== "not_a_reform") throw new Error("reforms " + unknownWhy.reforms.join(","));
if (unknown.selection().length) throw new Error("unknown id was treated as a benchmark");

const mixed = loadLab("?st=PA&on=adu,approval").whyRequest();
if (mixed.scenario !== "selection") throw new Error("mixed scenario " + mixed.scenario);
if (mixed.reforms.join(",") !== "adu,approval") throw new Error("mixed reforms " + mixed.reforms.join(","));

const empty = loadLab("?st=PA&on=none").whyRequest();
if (empty.scenario !== "selection" || empty.reforms.length) throw new Error("empty selection changed");

const single = loadLab("?st=PA&on=adu").whyRequest();
if (single.scenario !== "adu" || single.reforms.join(",") !== "adu") throw new Error("single reform changed");

const cell = loadLab("?st=PA&on=none").funnelCell;
if (cell(null, "delivered") !== "—") throw new Error("missing stage");
if (cell({}, "delivered") !== "—") throw new Error("missing value");
if (cell({ delivered: NaN }, "delivered") !== "—") throw new Error("NaN count");
if (cell({ completion: NaN }, "completion") !== "—") throw new Error("NaN ratio");
if (cell({ completion: "nope" }, "completion") !== "—") throw new Error("non-numeric ratio");
if (cell({ go_ahead_share: Infinity }, "go_ahead_share") !== "—") throw new Error("infinite share");
if (cell({ delivered: 12.4 }, "delivered") !== "12") throw new Error("count " + cell({ delivered: 12.4 }, "delivered"));
if (cell({ completion: 0.9 }, "completion") !== "90.0%") throw new Error("ratio " + cell({ completion: 0.9 }, "completion"));

const app = readFileSync(new URL("../../src/web/static/app.js", import.meta.url), "utf8");
const bandSandbox = { Number, Math, Object, isFinite };
createContext(bandSandbox);
runInContext(
  extractFunctions(app, ["oneDecimal", "permitVintageText", "formatBand"]) +
    "\nthis.formatBand = formatBand; this.permitVintageText = permitVintageText;",
  bandSandbox,
);
const trend = { name: "permit_growth_rate", label: "Annual permit trend", unit: "rate" };
if (bandSandbox.formatBand(-0.02, 0.03, trend) !== "0 (no trend)") {
  throw new Error("trend band " + bandSandbox.formatBand(-0.02, 0.03, trend));
}
if (bandSandbox.formatBand(-0, 0, trend) !== "0 (no trend)") throw new Error("signed zero trend");
if (bandSandbox.formatBand(0, 0, { name: "other", label: "Cap rate" }) !== "0") throw new Error("other zero band");
if (bandSandbox.formatBand(0.5, 1.5, { label: "Lag" }) !== "0.5 to 1.5") {
  throw new Error("wide band " + bandSandbox.formatBand(0.5, 1.5, { label: "Lag" }));
}
if (bandSandbox.permitVintageText(null) !== "—") throw new Error("missing vintage");
if (bandSandbox.permitVintageText({}) !== "—") throw new Error("blank vintage");
if (bandSandbox.permitVintageText({ permit_vintage: "BPS 2023-2025" }) !== "BPS 2023-2025") {
  throw new Error("vintage text");
}

console.log("browser qa ok");
