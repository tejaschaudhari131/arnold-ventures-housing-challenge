import { readFileSync } from "node:fs";
import { createContext, runInContext } from "node:vm";

const root = new URL("../../", import.meta.url);
function read(path) {
  return readFileSync(new URL(path, root), "utf8");
}

const sandbox = { console, Number, Math, Object, String, isFinite };
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
createContext(sandbox);
runInContext(read("src/web/static/fmt.js") + "\n" + read("src/web/static/frame.js"), sandbox);
const Frame = sandbox.StateframeFrame;
const Fmt = sandbox.StateframeFmt;
if (!Frame || !Fmt) throw new Error("frame did not load");

function load(code) {
  return JSON.parse(read("data/sample/lab/results_" + code + ".json"));
}

function lookup(doc, path) {
  return path.split(".").reduce(function (cur, key) {
    if (cur == null) return undefined;
    return cur[key];
  }, doc);
}

function binds(html) {
  const out = [];
  const re = /data-bind="([^"]+)">([^<]*)</g;
  let match;
  while ((match = re.exec(html))) out.push([match[1], match[2]]);
  return out;
}

function assertBound(html, doc, label) {
  binds(html).forEach(function (pair) {
    const value = lookup(doc, pair[0]);
    if (value == null || typeof value === "object") return;
    const numeric = Number(value);
    if (!isFinite(numeric)) return;
    const plain = pair[1].replace(/[+,]/g, "").replace("−", "-").replace("%", "");
    const shown = Number(plain);
    if (!isFinite(shown)) throw new Error(label + " unbound text " + pair[1] + " at " + pair[0]);
    const ratio = pair[1].indexOf("%") >= 0;
    const expected = ratio ? numeric * 100 : numeric;
    if (Math.abs(shown - expected) > 1.01) {
      throw new Error(label + " " + pair[0] + " showed " + pair[1] + " for " + value);
    }
  });
}

const scenarios = ["adu", "missing_middle", "parking", "fees", "package"];
for (const code of ["PA", "NH"]) {
  const doc = load(code);
  const sw = doc.statewide.results;
  for (const sid of scenarios) {
    const row = sw[sid];
    const opts = {
      sid: sid,
      status: "conditional",
      stateName: doc.name,
      endYear: "2031",
      label: sid,
      low: row.p10,
      high: row.p90,
      middle: row.central,
      baseline: sw.baseline.central,
      draws: doc.draws,
      paths: {
        low: "statewide.results." + sid + ".p10",
        high: "statewide.results." + sid + ".p90",
        middle: "statewide.results." + sid + ".central",
        baseline: "statewide.results.baseline.central",
        pct: "statewide.results." + sid + ".lift",
        endYear: "assumptions.end_year"
      }
    };
    const head = Frame.headlineParts(opts);
    if (head.html.indexOf("range-hero") > head.html.indexOf("middle-est")) {
      throw new Error(code + " " + sid + " middle appears before the range");
    }
    if (head.html.indexOf("data-bind=\"" + opts.paths.low) > head.html.indexOf("data-bind=\"" + opts.paths.middle)) {
      throw new Error(code + " " + sid + " middle bind precedes the range");
    }
    assertBound(head.html, doc, code + " headline " + sid);
    const funnel = Frame.funnelHtml({
      sid: sid,
      funnel: row.funnel,
      stateName: doc.name,
      label: sid,
      endYear: "2031",
      prefix: "statewide.results." + sid + ".funnel",
      middle: row.central,
      middlePath: "statewide.results." + sid + ".central",
      low: row.p10,
      high: row.p90,
      lowPath: "statewide.results." + sid + ".p10",
      highPath: "statewide.results." + sid + ".p90",
      feesLotHomes: row.host_delta,
      feesPath: "statewide.results." + sid + ".host_delta"
    });
    if (row.funnel == null) {
      if (funnel.indexOf(Frame.NOT_MODELLED) < 0) throw new Error(sid + " missing not-modelled copy");
      if (sid === "fees" && Math.abs(row.host_delta) >= 1 && funnel.indexOf("from lots") < 0) {
        throw new Error("fees lot note missing");
      }
      continue;
    }
    if (funnel.indexOf("not reported separately yet") >= 0) throw new Error("stale stage 3 copy");
    if (funnel.indexOf("<table") < 0 || funnel.indexOf("<caption>") < 0) throw new Error("funnel table missing");
    if (!/lots/.test(funnel) || !/homes/.test(funnel)) throw new Error("units missing");
    const fn = row.funnel;
    if (Math.abs(fn.delivered + fn.other_channels - row.central) > 1) {
      throw new Error(code + " " + sid + " delivered+other");
    }
    const gross = fn.gross;
    const base = fn.baseline_gross;
    for (const stage of [gross, base]) {
      if (!(stage.legal_fits >= stage.pays && stage.pays >= stage.go_ahead && stage.go_ahead >= stage.finishing)) {
        throw new Error(code + " " + sid + " not monotone");
      }
    }
    assertBound(funnel, doc, code + " funnel " + sid);
    const params = Object.keys(doc.statewide.one_at_a_time).map(function (name) {
      return { name: name, label: name, low: 0, high: 1, unit: "", tag: "assumed" };
    });
    const ranked = Frame.rankDrivers(doc.statewide.one_at_a_time, sid, params);
    const top = ranked.slice(0, 5).map(function (item) { return item.key; });
    const expected = params.map(function (spec, index) {
      const ends = doc.statewide.one_at_a_time[spec.name];
      return { key: spec.name, swing: Math.abs(ends.high[sid] - ends.low[sid]), order: index };
    }).sort(function (a, b) {
      if (b.swing !== a.swing) return b.swing - a.swing;
      return a.order - b.order;
    }).slice(0, 5).map(function (item) { return item.key; });
    if (top.join() !== expected.join()) throw new Error(code + " " + sid + " drivers " + top + " vs " + expected);
    const table = Frame.driversHtml({ sid: sid, label: sid, oat: doc.statewide.one_at_a_time, params: params, showAll: false });
    if (table.indexOf("Ranked at default settings") < 0) throw new Error("caption missing");
    const overridden = Frame.driversHtml({
      sid: sid, label: sid, oat: doc.statewide.one_at_a_time, params: params, hasOverrides: true, changed: {}
    });
    if (overridden.indexOf("Your changes are not reflected in this ranking.") < 0) throw new Error("override note");
    if (Frame.rankDrivers(doc.statewide.one_at_a_time, sid, params).map(function (item) { return item.key; }).join() !== ranked.map(function (item) { return item.key; }).join()) {
      throw new Error("ranks moved");
    }
  }
}

const ref = Frame.headlineParts({
  sid: "package",
  status: "reference",
  stateName: "Pennsylvania",
  endYear: "2031",
  low: 10,
  high: 20,
  middle: 15,
  baseline: 100,
  paths: { low: "statewide.results.package.p10", high: "statewide.results.package.p90", middle: "statewide.results.package.central", baseline: "statewide.results.baseline.central", pct: "x", endYear: "y" }
});
if (ref.html.indexOf("Reference range — from default assumptions, not recomputed") < 0) throw new Error("reference kicker");
if (ref.html.indexOf("not recomputed") < 0) throw new Error("not recomputed");
const emptyHead = Frame.headlineParts({ sid: "" }).html;
if (emptyHead.indexOf("+0") >= 0) throw new Error("empty headline shows +0");
if ((emptyHead.match(/pick a reform/gi) || []).length !== 1) throw new Error("pick a reform repeated: " + emptyHead);
const mix = Frame.miniTotal({ unmodeled: true, label: "Your package", low: null, high: null, middle: 8517 });
if (mix.indexOf("0 to 0") >= 0 || mix.indexOf("8,517") >= 0) throw new Error("mix total invented a sum: " + mix);
if (/not computed/i.test(mix)) throw new Error("mix sticky bar repeats Not computed: " + mix);
const mixHead = Frame.headlineParts({ unmodeled: true, sid: "selection", low: null, high: null, middle: 8517, paths: { middle: "statewide.results.selection.central" } });
if (mixHead.html.indexOf("selection") >= 0 || mixHead.html.indexOf("8,517") >= 0) throw new Error("mix headline bound a fake path");
if ((mixHead.html.match(/not computed/gi) || []).length !== 1) throw new Error("mix headline should say Not computed once: " + mixHead.html);
if (mixHead.live) throw new Error("mix live region repeats the headline");
const rankedSwing = Frame.rankDrivers(load("PA").statewide.one_at_a_time, "package", Object.keys(load("PA").statewide.one_at_a_time).map(function (name) {
  return { name: name, label: name, low: 0, high: 1, unit: "", tag: "assumed" };
}));
rankedSwing.slice(0, 5).forEach(function (row) {
  const ends = load("PA").statewide.one_at_a_time[row.key];
  if (Math.abs(row.swing - Math.abs(ends.high.package - ends.low.package)) > 0.01) {
    throw new Error("swing derivation " + row.key);
  }
});
const lift = Frame.headlineParts({
  sid: "adu", status: "conditional", stateName: "Pennsylvania", endYear: "2031",
  low: 10, high: 20, middle: 5, baseline: 100, draws: 10,
  paths: { low: "statewide.results.adu.p10", high: "statewide.results.adu.p90", middle: "statewide.results.adu.central", baseline: "statewide.results.baseline.central" }
});
if (!/data-bind="derived\.lift\.adu"/.test(lift.html)) throw new Error("lift is not bound to derived.lift");
if (/data-derived=/.test(lift.html)) throw new Error("lift still uses an unbound derived marker");
const mmDrivers = Frame.driversHtml({
  sid: "missing_middle",
  label: "Allow 2–6 homes on single-family lots",
  oat: load("PA").statewide.one_at_a_time,
  params: Object.keys(load("PA").statewide.one_at_a_time).map(function (name) {
    return { name: name, label: name, low: 0, high: 1, unit: "", tag: "assumed" };
  }),
  showAll: false
});
if (mmDrivers.indexOf("Share of owners who add 2–6 homes each year on lots where it pays off") < 0) {
  throw new Error("missing-middle driver kept ADU wording");
}
if (mmDrivers.indexOf("add an ADU") >= 0) throw new Error("missing-middle table uses ADU copy");
if (!/data-bind="derived\.swing\.hazard_homeowner_feasible\.missing_middle">9,721</.test(mmDrivers)) {
  throw new Error("9,721 is not bound to the missing-middle swing");
}
if (Frame.FUNNEL_UNAVAILABLE.indexOf("Funnel not available") < 0) throw new Error("screening funnel");
const screening = Frame.funnelHtml({ screening: true });
if (screening.indexOf(Frame.FUNNEL_UNAVAILABLE) < 0) throw new Error("screening funnel html");

const banned = ["74114", "74,114", "18023", "18,023", "13892", "13,892", "12188", "12,188"];
for (const file of ["src/web/static/lab.js", "src/web/static/frame.js", "src/web/static/brief.js", "src/web/static/lab.html", "src/web/static/brief.html", "src/web/static/app.js"]) {
  const text = read(file);
  banned.forEach(function (token) {
    if (text.indexOf(token) >= 0) throw new Error(file + " hard-codes " + token);
  });
  const literals = Array.from(text.matchAll(/"([^"\\]*)"|'([^'\\]*)'/g)).map(function (match) {
    return match[1] || match[2] || "";
  }).join("\n");
  const stripped = literals.replace(/not a forecast/gi, "").replace(/not forecasts/gi, "");
  ["predicts", "will produce", "forecast"].forEach(function (word) {
    if (stripped.toLowerCase().indexOf(word) >= 0) throw new Error(file + " says " + word);
  });
}

console.log("frame ux ok");
