/* State Housing Impact Note. Numbers come from the Lab results or the screening API. */
(function () {
  "use strict";

  var COUNTY = { PA: "Pennsylvania", NH: "New Hampshire" };
  var SCREENING = {
    CT: "Connecticut", WI: "Wisconsin", UT: "Utah", OR: "Oregon", HI: "Hawaii",
    AZ: "Arizona", VA: "Virginia", TN: "Tennessee", RI: "Rhode Island"
  };
  var ALIAS = { mm: "missing_middle", adu: "adu", parking: "parking", fees: "fees" };
  var SHORT = { missing_middle: "mm", adu: "adu", parking: "parking", fees: "fees" };
  var BILL_NAMES = {
    adu: "ADUs",
    missing_middle: "2–6 unit homes",
    parking: "No parking rules",
    fees: "Fee cap"
  };
  var Frame = window.StateframeFrame;
  var Fmt = window.StateframeFmt;
  var stateCode = "PA";
  var model = "county";
  var selected = new Set(["adu", "missing_middle", "parking", "fees"]);
  var catalog = null;
  var doc = null;

  var stateSelect = document.getElementById("brief-state");
  var memoMeta = document.getElementById("memo-meta");
  var answer = document.getElementById("answer");
  var topCountiesBody = document.getElementById("top-counties-body");
  var rentReliefBody = document.getElementById("rent-relief-body");
  var higher = document.getElementById("higher-list");
  var limits = document.getElementById("limits");
  var statusEl = document.getElementById("status");
  var full = document.getElementById("full-model");

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function fmtInt(n) {
    var v = Number(n);
    if (!isFinite(v)) return "—";
    return Math.round(v).toLocaleString("en-US");
  }

  function fmtSigned(n) {
    if (Fmt && Fmt.signedHomes) return Fmt.signedHomes(n);
    var v = Math.round(Number(n) || 0);
    return (v > 0 ? "+" : "") + v.toLocaleString("en-US");
  }

  function setStatus(text) { statusEl.textContent = text || ""; }

  function fillStates() {
    var html = "";
    Object.keys(COUNTY).forEach(function (code) {
      html += '<option value="' + code + '">' + COUNTY[code] + " (Step 2 Lot Lab)</option>";
    });
    Object.keys(SCREENING).forEach(function (code) {
      html += '<option value="' + code + '">' + SCREENING[code] + " (Step 1 Screen)</option>";
    });
    stateSelect.innerHTML = html;
  }

  function readUrl() {
    var q = new URLSearchParams(location.search);
    var st = (q.get("st") || "PA").toUpperCase();
    if (COUNTY[st] || SCREENING[st]) stateCode = st;
    model = q.get("model") === "screening" || SCREENING[stateCode] ? "screening" : "county";
    if (q.get("model") === "county" && COUNTY[stateCode]) model = "county";
    if (q.has("on")) {
      selected = new Set();
      var raw = q.get("on");
      if (raw && raw !== "none") {
        raw.split(",").forEach(function (part) {
          var id = ALIAS[part] || part;
          if (SHORT[id]) selected.add(id);
        });
      }
    } else {
      selected = new Set(["adu", "missing_middle", "parking", "fees"]);
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
    var onVal = ids.length ? ids.join(",") : "none";
    q.set("on", onVal);
    history.replaceState(null, "", "?" + q.toString());
    var target = model === "county" ? "/lab" : "/";
    full.href = target + "?" + q.toString() + "#results";
    var navScreen = document.getElementById("brief-nav-screener");
    if (navScreen) navScreen.href = "/?st=" + encodeURIComponent(stateCode) + "&on=" + encodeURIComponent(onVal);
    var navLab = document.getElementById("brief-nav-lab");
    if (navLab) {
      var labSt = COUNTY[stateCode] ? stateCode : "PA";
      navLab.href = "/lab?st=" + encodeURIComponent(labSt) + "&on=" + encodeURIComponent(onVal);
    }
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

  function activeBillsText() {
    if (!selected.size) return "None picked yet";
    if (selected.size === 4) return "All 4 core bills";
    var list = [];
    selected.forEach(function (k) {
      if (BILL_NAMES[k]) list.push(BILL_NAMES[k]);
    });
    return list.join(", ");
  }

  function renderMemoMeta() {
    if (!memoMeta) return;
    var stName = COUNTY[stateCode] || SCREENING[stateCode] || stateCode;
    var lensText = model === "county" ? "Step 2 Lot Lab" : "Step 1 Macro Screen";
    var yr = endYear();
    var winText = yr ? ("5 yrs · to " + yr) : "5-year view";
    memoMeta.innerHTML =
      '<div class="memo-cell"><span>To</span><strong>State Lawmakers</strong></div>' +
      '<div class="memo-cell"><span>State</span><strong>' + esc(stName + " (" + stateCode + ")") + "</strong></div>" +
      '<div class="memo-cell"><span>Model</span><strong>' + esc(lensText) + "</strong></div>" +
      '<div class="memo-cell"><span>Bills on (' + esc(winText) + ")</span><strong>" + esc(activeBillsText()) + "</strong></div>";
  }

  function renderTopCounties(rows) {
    if (!topCountiesBody) return;
    if (!selected.size) {
      topCountiesBody.innerHTML = '<p class="note-empty">Pick a bill above to see top counties.</p>';
      return;
    }
    if (!rows || !rows.length) {
      topCountiesBody.innerHTML = '<p class="note-empty">County totals are loading.</p>';
      return;
    }
    var sorted = rows.slice().sort(function (a, b) { return b.added - a.added; }).slice(0, 5);
    var body = sorted.map(function (r) {
      return "<tr><td>" + esc(r.name) + "</td><td>" + fmtInt(r.base) + "</td><td><strong>" +
        esc(fmtSigned(r.added)) + "</strong></td></tr>";
    }).join("");
    topCountiesBody.innerHTML =
      '<table class="note-table">' +
      "<thead><tr><th>County</th><th>5-yr base</th><th>Added</th></tr></thead>" +
      "<tbody>" + body + "</tbody></table>" +
      '<p class="note-foot">Top five counties by extra homes over five years.</p>';
  }

  function renderRentRelief(ins) {
    if (!rentReliefBody) return;
    if (!ins || !ins.affordability_screen) {
      rentReliefBody.innerHTML = '<p class="note-empty">Rent figures are not loaded right now.</p>';
      return;
    }
    var aff = ins.affordability_screen;
    var obs = aff.observed_context || {};
    var protos = (aff.prototypes || []).slice(0, 2);
    var rowsHtml = protos.map(function (p) {
      var m = p.metrics || {};
      var saved = Math.round((Number(m.breakeven_rent_before) || 0) - (Number(m.breakeven_rent_after) || 0));
      var savedTxt = saved > 0 ? ("-$" + fmtInt(saved) + "/mo") : "$0/mo";
      var shortName = /ADU/i.test(p.label) ? "Backyard ADU" : "Small 2–4 plex";
      return "<tr><td>" + esc(shortName) + "</td><td>$" + fmtInt(m.breakeven_rent_before) +
        "</td><td><strong>$" + fmtInt(m.breakeven_rent_after) + "</strong></td><td>" + esc(savedTxt) + "</td></tr>";
    }).join("");
    rentReliefBody.innerHTML =
      '<p class="note-sub">Typical pay: <strong>$' + fmtInt(obs.median_household_income) +
      "/yr</strong> · Typical rent: <strong>$" + fmtInt(obs.median_gross_rent) + "/mo</strong>.</p>" +
      '<table class="note-table">' +
      "<thead><tr><th>New home</th><th>Old cost</th><th>With bill</th><th>Change</th></tr></thead>" +
      "<tbody>" + rowsHtml + "</tbody></table>" +
      '<p class="note-foot">Monthly rent needed to cover build costs, not a price quote.</p>';
  }

  function screeningReforms() {
    return {
      adu: selected.has("adu") ? 1 : 0,
      missing_middle: selected.has("missing_middle") ? 1 : 0,
      tod: 0,
      parking: selected.has("parking") ? 1 : 0,
      fees: selected.has("fees") ? 1 : 0
    };
  }

  function countyRowsFromLab(mixDoc) {
    var id = sid();
    var mixMap = {};
    if (mixDoc && mixDoc.counties) {
      mixDoc.counties.forEach(function (mc) { mixMap[mc.fips] = mc; });
    }
    return ((doc && doc.counties) || []).map(function (c) {
      var res = c.results || {};
      var base = res.baseline ? Number(res.baseline.central) || 0 : 0;
      var added = 0;
      if (id && res[id]) {
        added = Number(res[id].central) || 0;
      } else if (mixMap[c.fips]) {
        added = Number(mixMap[c.fips].central) || 0;
      } else {
        selected.forEach(function (k) {
          if (res[k]) added += Number(res[k].central) || 0;
        });
      }
      return { name: c.name, base: base, added: added };
    });
  }

  function countyRowsFromScreening(payload) {
    return ((payload && payload.counties) || []).map(function (c) {
      return {
        name: c.name,
        base: Number(c.baseline_completions) || 0,
        added: Number(c.combined) || 0
      };
    });
  }

  function renderCounty(mixDoc, insDoc) {
    renderMemoMeta();
    renderRentRelief(insDoc);
    var id = sid();
    var sw = doc.statewide.results;
    var row = id && id !== "selection" ? sw[id] : null;
    var name = COUNTY[stateCode];
    if (!selected.size) {
      answer.innerHTML = Frame.briefAnswer({ sid: "" });
      renderTopCounties([]);
      higher.innerHTML = "";
      limits.innerHTML = Frame.limitsHtml({ sid: "", ratios: catalog.completion_ratios });
      return;
    }
    renderTopCounties(countyRowsFromLab(mixDoc));
    if (selected.size > 1 && selected.size < 4) {
      if (!mixDoc || !mixDoc.statewide) {
        answer.innerHTML = "<p>Pick one change, or all four, to see a number.</p>";
        higher.innerHTML = "";
        limits.innerHTML = "";
        return;
      }
      var msw = mixDoc.statewide;
      answer.innerHTML = Frame.briefAnswer({
        sid: "mix",
        status: "unavailable",
        stateName: name,
        endYear: endYear(),
        label: "Your mix",
        low: null,
        high: null,
        middle: msw.central,
        baseline: msw.baseline,
        draws: doc.draws,
        paths: {
          middle: "mix.statewide.central",
          baseline: "statewide.results.baseline.central",
          pct: "mix.statewide.lift",
          endYear: "assumptions.end_year"
        }
      });
      higher.innerHTML = "<li>Pick one change, or all four, to rank what moves the result most.</li>";
      limits.innerHTML = Frame.limitsHtml({ sid: "package", ratios: catalog.completion_ratios });
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
      parkingPath: "by_name.parking_market_urban.central"
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

  function renderScreening(payload, sens, insDoc) {
    renderMemoMeta();
    renderRentRelief(insDoc);
    if (!selected.size) {
      answer.innerHTML = Frame.briefAnswer({ sid: "" });
      renderTopCounties([]);
      higher.innerHTML = "";
      limits.innerHTML = "";
      return;
    }
    renderTopCounties(countyRowsFromScreening(payload));
    var name = SCREENING[stateCode] || COUNTY[stateCode] || stateCode;
    var middle = payload.scenarios && payload.scenarios.combined
      ? payload.scenarios.combined.incremental_completions : null;
    var mc = sens && sens.monte_carlo ? sens.monte_carlo : null;
    answer.innerHTML = Frame.briefAnswer({
      screening: true,
      screeningMiddle: middle,
      low: mc ? mc.p10 : null,
      high: mc ? mc.p90 : null,
      stateName: name,
      endYear: endYear()
    });
    var topRows = (sens && sens.tornado && sens.tornado.parameters ? sens.tornado.parameters : []).slice(0, 3);
    if (topRows.length && window.StateframeFmt) {
      higher.innerHTML = topRows.map(function (row) {
        var reach = Math.max(Number(row.low) || 0, Number(row.high) || 0);
        return "<li>Changing " + esc(String(row.label || row.name).toLowerCase()) +
          " within its tested range could push the total to about " +
          window.StateframeFmt.signedHomes(reach) + ".</li>";
      }).join("");
    } else {
      higher.innerHTML = "<li>Open the full model to test each setting on its own.</li>";
    }
    limits.innerHTML = "<section class=\"limits\"><h3>What this can't tell you</h3><ul>" +
      "<li>These are estimates under stated assumptions, not predictions.</li>" +
      "<li>They say nothing about prices, rents, or who gets the homes.</li></ul>" +
      "<p>" + esc(Frame.FUNNEL_UNAVAILABLE) + "</p></section>";
  }

  function load() {
    writeUrl();
    renderMemoMeta();
    var reforms = screeningReforms();
    var assumptions = catalog ? Promise.resolve(catalog) : fetch("/api/lab/assumptions").then(function (res) { return res.json(); });
    var insightsReq = fetch("/api/insights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: stateCode, reforms: reforms })
    }).then(function (res) { return res.ok ? res.json() : null; }).catch(function () { return null; });

    if (model !== "county" && !selected.size) {
      setStatus("Updating results");
      answer.setAttribute("aria-busy", "true");
      Promise.all([assumptions, insightsReq]).then(function (parts) {
        catalog = parts[0];
        renderScreening({}, null, parts[1]);
        answer.setAttribute("aria-busy", "false");
        setStatus("");
      }).catch(function () {
        answer.setAttribute("aria-busy", "false");
        setStatus("");
      });
      return;
    }
    setStatus("Updating results");
    answer.setAttribute("aria-busy", "true");
    var pending = model === "county"
      ? fetch("/api/lab/results?state=" + stateCode).then(function (res) { return res.json(); })
      : fetch("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: stateCode, reforms: reforms })
      }).then(function (res) { return res.json(); });
    var extra = model === "county"
      ? (selected.size > 1 && selected.size < 4
        ? fetch("/api/lab/mix", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state: stateCode, reforms: Array.from(selected) })
        }).then(function (res) { return res.ok ? res.json() : null; }).catch(function () { return null; })
        : Promise.resolve(null))
      : fetch("/api/sensitivity", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: stateCode, scenario: "combined", draws: 80, reforms: reforms })
      }).then(function (res) { return res.ok ? res.json() : null; }).catch(function () { return null; });
    Promise.all([pending, assumptions, extra, insightsReq]).then(function (parts) {
      doc = parts[0];
      catalog = parts[1];
      if (model === "county") renderCounty(parts[2], parts[3]);
      else renderScreening(doc, parts[2], parts[3]);
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
      setStatus("Select and copy the page link.");
    }
  });
  load();
})();
