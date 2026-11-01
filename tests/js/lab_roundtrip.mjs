import { readFileSync } from "node:fs";
import { createContext, runInContext } from "node:vm";

const search = process.argv[2] || "?st=PA&on=none&ov=hazard_homeowner_feasible:0.0062";
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
  location: {
    search,
    hash: "",
    href: hrefBox.value,
  },
  history: {
    replaceState(_state, _title, next) {
      hrefBox.value = "http://127.0.0.1/lab" + next;
      sandbox.location.href = hrefBox.value;
    },
  },
  fetch() {
    return Promise.reject(new Error("offline"));
  },
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
if (!api) throw new Error("StateframeLab was not exported");
const selection = api.selection();
const overrides = api.overrideMap();
if (selection.length !== 0) {
  throw new Error("empty selection became " + JSON.stringify(selection));
}
if (overrides.hazard_homeowner_feasible !== 0.0062) {
  throw new Error("override was dropped: " + JSON.stringify(overrides));
}
api.writeUrl();
if (!hrefBox.value.includes("on=none")) throw new Error("url lost the empty selection: " + hrefBox.value);
if (!hrefBox.value.includes("hazard_homeowner_feasible")) throw new Error("url lost the override: " + hrefBox.value);
const labeled = api.describeRange({ p10: 10, p90: 20, interval_status: "reference" });
if (!labeled.includes("Reference range (defaults)")) throw new Error(labeled);
if (labeled.includes("—")) throw new Error("range used a dash: " + labeled);
const missing = api.describeRange({ interval_status: "unavailable" });
if (missing !== "Likely range unavailable") throw new Error(missing);
console.log("ok " + hrefBox.value);
