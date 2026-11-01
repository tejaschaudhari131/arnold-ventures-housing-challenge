import { readFileSync } from "node:fs";
import { createContext, runInContext } from "node:vm";

function el() {
  return {
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
  location: { search: "", hash: "", href: "http://127.0.0.1/lab" },
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
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.window.matchMedia = () => ({ matches: true });
createContext(sandbox);
const source = readFileSync(new URL("../../src/web/static/lab.js", import.meta.url), "utf8");
runInContext(source, sandbox);
const api = sandbox.StateframeLab;
if (!api || typeof api.buildCountyCsv !== "function") throw new Error("buildCountyCsv was not exported");

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(field);
      if (row.length > 1 || row[0] !== "") rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function subsets(ids) {
  const out = [[]];
  ids.forEach((id) => {
    const extra = out.map((row) => row.concat(id));
    extra.forEach((row) => out.push(row));
  });
  return out;
}

const part = {
  central: 12.4,
  p10: 1.1,
  p90: 20.2,
  zoning_low: 3,
  zoning_high: 9,
  acs_moe: 0.4,
  eligible: 10,
  feasible: 2,
};
const county = {
  fips: "42001",
  name: '=Say "hi"',
  top_benchmark_pair: { close_call: false },
  results: {
    adu: part,
    missing_middle: part,
    parking: part,
    fees: part,
    package: part,
    baseline: part,
  },
};

const reforms = ["adu", "missing_middle", "parking", "fees"];
for (const ids of subsets(reforms)) {
  const text = api.buildCountyCsv([county], ids, { lockedCounties: [county] });
  if (text.split(/\r?\n/)[0].startsWith("#")) throw new Error("comment line before the header");
  const rows = parseCsv(text);
  const width = rows[0].length;
  const expected = ids.length === 1 || ids.length === 4 ? api.scenarioColumns : api.mixColumns;
  if (rows[0].join("|") !== expected.join("|")) {
    throw new Error("columns " + JSON.stringify(rows[0]) + " for " + JSON.stringify(ids));
  }
  rows.forEach((row, index) => {
    if (row.length !== width) {
      throw new Error("row " + index + " has " + row.length + " fields, header has " + width + " for " + JSON.stringify(ids));
    }
  });
  if (ids.length === 2 || ids.length === 3) {
    if (rows[1][4] !== "simple sum of standalone results, not modelled jointly") {
      throw new Error("central basis was split: " + JSON.stringify(rows[1]));
    }
  }
  if (rows[1][1] !== '\'=Say "hi"') throw new Error("formula guard failed: " + rows[1][1]);
}

const slow = api.sliderValueText({ unit: "per year" }, 0.001475);
const slower = api.sliderValueText({ unit: "per year" }, 0.0006);
if (slow === slower) throw new Error("hazards collapsed to " + slow);
if (slow !== "0.00148 a year") throw new Error("0.001475 showed " + slow);
if (slower !== "0.000600 a year") throw new Error("0.0006 showed " + slower);

const tip = api.tooltipMarkup("calculated", "Arithmetic in the model.");
const ids = [...tip.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
const refs = [...tip.matchAll(/aria-describedby="([^"]+)"/g)].map((match) => match[1]);
if (!refs.length) throw new Error("tooltip has no aria-describedby");
refs.forEach((ref) => {
  ref.split(/\s+/).forEach((token) => {
    if (!ids.includes(token)) throw new Error("missing described-by target " + token + " in " + tip);
  });
});

console.log("ok " + subsets(reforms).length + " subsets");
