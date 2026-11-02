/* Legislator quick answer. Numbers come from the Lab results or the screening API. */
(function () {
  "use strict";

  var COUNTY = { PA: "Pennsylvania", NH: "New Hampshire" };
  var SCREENING = {
    CT: "Connecticut", WI: "Wisconsin", UT: "Utah", OR: "Oregon", HI: "Hawaii",
    AZ: "Arizona", VA: "Virginia", TN: "Tennessee", RI: "Rhode Island"
  };
  var ALIAS = { mm: "missing_middle", adu: "adu", parking: "parking", fees: "fees" };
  var SHORT = { missing_middle: "mm", adu: "adu", parking: "parking", fees: "fees" };
  var Frame = window.StateframeFrame;
  var stateCode = "PA";
  var model = "county";
  var selected = new Set();
  var catalog = null;
  var doc = null;

  var stateSelect = document.getElementById("brief-state");
  var answer = document.getElementById("answer");
  var higher = document.getElementById("higher-list");
  var limits = document.getElementById("limits");
  var statusEl = document.getElementById("status");
  var full = document.getElementById("full-model");

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function setStatus(text) { statusEl.textContent = text || ""; }

  function fillStates() {
    var html = "";
    Object.keys(COUNTY).forEach(function (code) {
      html += '<option value="' + code + '">' + COUNTY[code] + "</option>";
    });
    Object.keys(SCREENING).forEach(function (code) {
      html += '<option value="' + code + '">' + SCREENING[code] + " — rough estimate</option>";
    });
    stateSelect.innerHTML = html;
  }

  function readUrl() {
    var q = new URLSearchParams(location.search);
    var st = (q.get("st") || "PA").toUpperCase();
    if (COUNTY[st] || SCREENING[st]) stateCode = st;
    model = q.get("model") === "screening" || SCREENING[stateCode] ? "screening" : "county";
    if (q.get("model") === "county" && COUNTY[stateCode]) model = "county";
    selected = new Set();
    var raw = q.get("on");
    if (raw && raw !== "none") {
      raw.split(",").forEach(function (part) {
        var id = ALIAS[part] || part;
        if (SHORT[id]) selected.add(id);
      });
    }
    stateSelect.value = stateCode;
    document.querySelectorAll('#brief-form input[name="on"]').forEach(function (box) {
      box.checked = selected.has(box.value);
    });
  }

  function writeUrl() {
    var q = new URLSearchParams();
    q.set("st", stateCode);
    q.set("model", model);
    var ids = [];
    selected.forEach(function (id) { ids.push(SHORT[id] || id); });
    q.set("on", ids.length ? ids.join(",") : "none");
    history.replaceState(null, "", "?" + q.toString());
    var target = model === "county" ? "/lab" : "/";
    full.href = target + "?" + q.toString() + "#results";
  }

  function sid() {
    if (selected.size === 1) return Array.from(selected)[0];
    if (selected.size === 4) return "package";
    return "";
  }

  function endYear() {
    if (!catalog || !catalog.window_start) return "";
    var start = Number(String(catalog.window_start).slice(0, 4));
    return String(start + Number(catalog.horizon_years) - 1);
  }

  function renderCounty() {
    var id = sid();
    var sw = doc.statewide.results;
    var row = id && id !== "selection" ? sw[id] : null;
    var name = COUNTY[stateCode];
    if (selected.size > 1 && selected.size < 4) {
      answer.innerHTML = "<p>Pick one change, or all four. A mix is not modeled.</p>";
      higher.innerHTML = "";
      limits.innerHTML = "";
      return;
    }
    var opts = {
      sid: id,
      status: row && row.interval_status,
      stateName: name,
      endYear: endYear(),
      label: id || "",
      low: row && row.p10,
      high: row && row.p90,
      middle: row && row.central,
      baseline: sw.baseline.central,
      draws: doc.draws,
      paths: {
        low: "statewide.results." + id + ".p10",
        high: "statewide.results." + id + ".p90",
        middle: "statewide.results." + id + ".central",
        baseline: "statewide.results.baseline.central",
        pct: "statewide.results." + id + ".lift",
        endYear: "assumptions.end_year"
      }
    };
    answer.innerHTML = Frame.briefAnswer(opts);
    var drivers = id ? Frame.rankDrivers(doc.statewide.one_at_a_time, id, catalog.parameters || []) : [];
    higher.innerHTML = Frame.driverSentences(drivers, id);
    limits.innerHTML = id ? Frame.limitsHtml({
      sid: id,
      drivers: drivers,
      driverSid: id,
      ratios: catalog.completion_ratios,
      low: opts.low,
      high: opts.high,
      baseline: opts.baseline,
      lowPath: opts.paths.low,
      highPath: opts.paths.high,
      parkingText: parkingText(),
      parkingPath: "parameters.parking_market_urban.central"
    }) : Frame.limitsHtml({ sid: "", ratios: catalog.completion_ratios });
  }

  function parkingText() {
    var spec = null;
    (catalog.parameters || []).forEach(function (row) {
      if (row.name === "parking_market_urban") spec = row;
    });
    if (!spec) return "";
    return String(Math.round(Number(spec.central) * 100) / 100);
  }

  function renderScreening(payload) {
    var name = SCREENING[stateCode] || COUNTY[stateCode] || stateCode;
    var middle = payload.scenarios && payload.scenarios.combined
      ? payload.scenarios.combined.incremental_completions : null;
    answer.innerHTML = Frame.briefAnswer({
      screening: true,
      screeningMiddle: middle,
      stateName: name,
      endYear: ""
    });
    higher.innerHTML = "<li>A rough estimate does not rank assumptions.</li>";
    limits.innerHTML = "<section class=\"limits\"><h3>What this can't tell you</h3><ul>" +
      "<li>These are estimates under stated assumptions, not predictions.</li>" +
      "<li>They say nothing about prices, rents, or who gets the homes.</li></ul>" +
      "<p>" + esc(Frame.FUNNEL_UNAVAILABLE) + "</p></section>";
  }

  function load() {
    writeUrl();
    setStatus("Updating results");
    answer.setAttribute("aria-busy", "true");
    var pending = model === "county"
      ? fetch("/api/lab/results?state=" + stateCode).then(function (res) { return res.json(); })
      : fetch("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: stateCode })
      }).then(function (res) { return res.json(); });
    var assumptions = catalog ? Promise.resolve(catalog) : fetch("/api/lab/assumptions").then(function (res) { return res.json(); });
    Promise.all([pending, assumptions]).then(function (parts) {
      doc = parts[0];
      catalog = parts[1];
      if (model === "county") renderCounty();
      else renderScreening(doc);
      answer.setAttribute("aria-busy", "false");
      setStatus("");
    }).catch(function () {
      answer.setAttribute("aria-busy", "false");
      answer.innerHTML = '<p role="alert">Could not compute this scenario. Your settings are saved in the link.</p>';
      setStatus("");
    });
  }

  fillStates();
  readUrl();
  stateSelect.addEventListener("change", function () {
    stateCode = stateSelect.value;
    model = SCREENING[stateCode] ? "screening" : "county";
    load();
  });
  document.querySelectorAll('#brief-form input[name="on"]').forEach(function (box) {
    box.addEventListener("change", function () {
      if (box.checked) selected.add(box.value);
      else selected.delete(box.value);
      load();
    });
  });
  document.getElementById("print-brief").addEventListener("click", function () { window.print(); });
  document.getElementById("copy-link").addEventListener("click", function () {
    var url = location.href;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(function () { setStatus("Link copied"); });
    } else {
      setStatus("Couldn't copy — select the link below");
    }
  });
  load();
})();
