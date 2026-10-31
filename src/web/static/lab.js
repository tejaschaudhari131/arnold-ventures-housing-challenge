/* Small Homes Policy Lab client. Locked results load first. One slider
   recomputes central, zoning, and ACS MOE; the envelope stays locked. */
(function () {
  "use strict";

  var ORDER = ["adu", "missing_middle", "parking", "fees", "package", "approval"];
  var WALK = [
    { title: "Pennsylvania is loaded", text: "All 67 counties and four Handbook scenarios are already computed. Baseline is 111,016 five-year completions. Unknown zoning is a prior, never zero." },
    { title: "Pick a reform", text: "Start with ADUs, Handbook benchmark 1: one detached or semi-detached ADU of at least 600 sq ft, no added parking." },
    { title: "Open Allegheny County", text: "Allegheny is the walkthrough. Pittsburgh's October 2026 ADU ordinance is observed; the rest of the county is unknown." },
    { title: "Why this result?", text: "Every input is tagged observed, assumed, or calculated. The ADU pro forma is illustrative." },
    { title: "Change one assumption", text: "Move the homeowner uptake hazard. Central, zoning, and ACS MOE recompute. The p10–p90 envelope does not." },
    { title: "Export a brief", text: "Download Markdown, HTML, or a county CSV. The brief states the ranking, the close call, and what would change it." }
  ];

  var stateCode = "PA";
  var scenarioId = "adu";
  var selectedFips = "42003";
  var locked = null;
  var live = null;
  var geoDoc = null;
  var catalog = null;
  var whyDoc = null;
  var overrides = {};
  var walkStep = 0;
  var whyOpen = false;
  var timer = null;
  var requestId = 0;
  var aduCompare = null;

  var statusEl = document.getElementById("status");
  var stateList = document.getElementById("state-list");
  var headline = document.getElementById("headline");
  var cards = document.getElementById("cards");
  var mapStage = document.getElementById("map-stage");
  var mapTitle = document.getElementById("map-title");
  var countyDetail = document.getElementById("county-detail");
  var countyBody = document.getElementById("county-body");
  var sliders = document.getElementById("sliders");
  var whyEl = document.getElementById("why");
  var whyBody = document.getElementById("why-body");
  var envelopeNote = document.getElementById("envelope-note");

  function setStatus(text) { statusEl.textContent = text || ""; }

  function integer(value) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    return Math.round(n).toLocaleString("en-US");
  }

  function money(value) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    return "$" + Math.round(n).toLocaleString("en-US");
  }

  function pct(value) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    return (100 * n).toFixed(1) + "%";
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function tag(kind) {
    return '<abbr class="tag ' + kind + '" title="' + kind + '">' + kind + "</abbr>";
  }

  function scenarioLabel(sid) {
    var row = (locked && locked.scenarios || []).filter(function (s) { return s.id === sid; })[0];
    return row ? row.short : sid;
  }

  function docStatewide() {
    return live ? live.statewide : locked.statewide;
  }

  function docCounties() {
    return live ? live.counties : locked.counties;
  }

  function countyRow(fips) {
    return docCounties().filter(function (c) { return c.fips === fips; })[0];
  }

  function cell(row, sid) {
    return row.results[sid] || row.results.baseline;
  }

  function lockedCell(fips, sid) {
    var row = locked.counties.filter(function (c) { return c.fips === fips; })[0];
    return row ? row.results[sid] : null;
  }

  function signed(value) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    var text = integer(Math.abs(n));
    return (n > 0 ? "+" : n < 0 ? "−" : "") + text;
  }

  function get(path) {
    return fetch(path).then(function (res) {
      if (!res.ok) return res.json().then(function (body) { throw new Error(body.error || res.statusText); });
      return res.json();
    });
  }

  function post(path, payload) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (!res.ok) return res.json().then(function (body) { throw new Error(body.error || res.statusText); });
      return res.json();
    });
  }

  function fillAduFeeNote() {
    var el = document.getElementById("adu-fee-note");
    if (!el || !aduCompare) return;
    el.innerHTML = aduCompare.notes.lab_html;
  }

  function loadAll() {
    var id = ++requestId;
    setStatus("Loading locked Lab results…");
    return Promise.all([
      get("/api/lab/results?state=" + stateCode),
      get("/api/lab/geo?state=" + stateCode),
      catalog ? Promise.resolve(catalog) : get("/api/lab/assumptions"),
      aduCompare ? Promise.resolve(aduCompare) : get("/api/adu-compare?state=PA")
    ]).then(function (parts) {
      if (id !== requestId) return;
      locked = parts[0];
      geoDoc = parts[1];
      catalog = parts[2];
      aduCompare = parts[3];
      live = null;
      overrides = {};
      if (stateCode === "PA") selectedFips = selectedFips || "42003";
      else if (!countyRow(selectedFips)) selectedFips = locked.counties[0].fips;
      fillAduFeeNote();
      renderAll();
      if (whyOpen) loadWhy();
      setStatus("");
    }).catch(function (err) {
      setStatus(err.message);
    });
  }

  function renderAll() {
    renderStates();
    renderHeadline();
    renderCards();
    renderMap();
    renderTable();
    renderSliders();
    renderWalk();
  }

  function renderStates() {
    stateList.innerHTML = ["PA", "NH"].map(function (code) {
      var name = code === "PA" ? "Pennsylvania" : "New Hampshire";
      var role = code === "PA" ? "primary" : "portability";
      return '<button type="button" class="state-btn' + (code === stateCode ? " active" : "") +
        '" data-state="' + code + '"><strong>' + name + "</strong><span>" + role + "</span></button>";
    }).join("");
    stateList.querySelectorAll("[data-state]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        stateCode = btn.getAttribute("data-state");
        selectedFips = stateCode === "PA" ? "42003" : null;
        walkStep = 0;
        loadAll();
      });
    });
  }

  function renderHeadline() {
    var sw = docStatewide();
    var row = sw.results[scenarioId] || sw.results.adu;
    var env = locked.statewide.results[scenarioId] || locked.statewide.results.adu;
    var pair = sw.top_benchmark_pair;
    var cover = (live && live.coverage) || locked.coverage;
    var badge = pair.close_call
      ? '<span class="badge-close">Close call — ' + escapeHtml(scenarioLabel(pair.leader)) + " vs " + escapeHtml(scenarioLabel(pair.trailer)) + "</span>"
      : '<span class="badge-unknown">Ranking holds</span>';
    headline.innerHTML =
      stat("Selected increment", signed(row.central), "calculated") +
      stat("Eligible capacity", integer(row.eligible), "calculated") +
      stat("Feasible capacity", integer(row.feasible), "calculated") +
      stat("Baseline", integer(sw.results.baseline.central), "calculated") +
      '<div class="stat"><div class="k">Uncertainty (kept separate)</div>' +
      "<div class='s'>Envelope " + integer(env.p10) + "–" + integer(env.p90) + tag("assumed") + "</div>" +
      "<div class='s'>Zoning " + integer(row.zoning_low) + "–" + integer(row.zoning_high) + tag("assumed") + "</div>" +
      "<div class='s'>ACS MOE ±" + integer(row.acs_moe) + tag("observed") + "</div></div>" +
      '<div class="stat"><div class="k">Coverage and ranking</div>' +
      "<div class='s'>ADU evidence " + pct(cover.adu) + " · 2–6 homes " + pct(cover.mm) + "</div>" +
      "<div class='s'>" + badge + "</div>" +
      "<div class='s'>" + escapeHtml(sw.benchmark_ranking.map(scenarioLabel).join(" > ")) + "</div></div>";
  }

  function stat(label, value, kind) {
    return '<div class="stat"><div class="k">' + escapeHtml(label) + "</div>" +
      '<div class="v">' + value + tag(kind) + "</div></div>";
  }

  function renderCards() {
    cards.innerHTML = (locked.scenarios || []).filter(function (s) { return s.id !== "baseline"; }).map(function (s) {
      var row = docStatewide().results[s.id];
      var extra = s.kind === "extra" ? '<span class="pill t2">extra</span>' : '<span class="pill t1">benchmark</span>';
      return '<button type="button" class="scenario-card' + (s.id === scenarioId ? " selected" : "") +
        '" data-sid="' + s.id + '"><div class="card-top"><h3>' + escapeHtml(s.label) + "</h3>" + extra +
        "</div><p class='plain'>" + signed(row.central) + " vs Baseline" + tag("calculated") + "</p></button>";
    }).join("");
    cards.querySelectorAll("[data-sid]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        scenarioId = btn.getAttribute("data-sid");
        if (walkStep === 1) walkStep = 2;
        renderAll();
        if (whyOpen) loadWhy();
      });
    });
  }

  function colorFor(value, maxAbs) {
    if (!maxAbs) return "#d4cbb8";
    var t = Math.max(-1, Math.min(1, value / maxAbs));
    if (t >= 0) {
      return "rgb(" + Math.round(228 - 213 * t) + "," + Math.round(224 - 117 * t) + "," + Math.round(208 - 130 * t) + ")";
    }
    return "rgb(" + Math.round(228 + 26 * t) + "," + Math.round(224 + 140 * t) + "," + Math.round(208 + 80 * t) + ")";
  }

  function projectBounds(counties) {
    var minX = 180, minY = 90, maxX = -180, maxY = -90;
    counties.forEach(function (c) {
      (c.rings || []).forEach(function (ring) {
        ring.forEach(function (pt) {
          minX = Math.min(minX, pt[0]); maxX = Math.max(maxX, pt[0]);
          minY = Math.min(minY, pt[1]); maxY = Math.max(maxY, pt[1]);
        });
      });
    });
    return { minX: minX, minY: minY, maxX: maxX, maxY: maxY };
  }

  function renderMap() {
    if (!geoDoc) { mapStage.textContent = "Boundaries are still loading."; return; }
    mapTitle.textContent = locked.name + " counties";
    var box = projectBounds(geoDoc.counties);
    var width = 800;
    var height = 520;
    var midLat = (box.minY + box.maxY) / 2 * Math.PI / 180;
    var xspan = (box.maxX - box.minX) * Math.cos(midLat);
    var yspan = box.maxY - box.minY;
    var pad = 16;
    var scale = Math.min((width - 2 * pad) / xspan, (height - 2 * pad) / yspan);
    function xy(lon, lat) {
      return [
        pad + (lon - box.minX) * Math.cos(midLat) * scale,
        height - pad - (lat - box.minY) * scale
      ];
    }
    var maxAbs = 0;
    docCounties().forEach(function (c) {
      maxAbs = Math.max(maxAbs, Math.abs(cell(c, scenarioId).central));
    });
    var paths = geoDoc.counties.map(function (c) {
      var row = countyRow(c.fips);
      var value = row ? cell(row, scenarioId).central : 0;
      var d = (c.rings || []).map(function (ring) {
        return ring.map(function (pt, i) {
          var p = xy(pt[0], pt[1]);
          return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1);
        }).join(" ") + " Z";
      }).join(" ");
      var selected = c.fips === selectedFips;
      return '<path class="county' + (selected ? " selected" : "") + '" role="button" tabindex="0" data-fips="' +
        c.fips + '" d="' + d + '" fill="' + colorFor(value, maxAbs) + '"><title>' +
        escapeHtml(c.name) + " " + signed(value) + "</title></path>";
    }).join("");
    mapStage.innerHTML = '<svg viewBox="0 0 ' + width + " " + height +
      '" role="img" aria-label="County map colored by the selected scenario">' +
      '<rect width="100%" height="100%" fill="#f7f3ea"></rect>' + paths + "</svg>";
    mapStage.querySelectorAll("[data-fips]").forEach(function (node) {
      function choose() {
        selectedFips = node.getAttribute("data-fips");
        if (walkStep === 2) walkStep = 3;
        renderMap();
        renderTable();
        renderHeadline();
        if (whyOpen) loadWhy();
      }
      node.addEventListener("click", choose);
      node.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); }
      });
    });
    renderCountyDetail();
  }

  function renderCountyDetail() {
    var row = selectedFips ? countyRow(selectedFips) : null;
    if (!row) { countyDetail.hidden = true; return; }
    var current = cell(row, scenarioId);
    var env = lockedCell(row.fips, scenarioId);
    var pair = row.top_benchmark_pair || locked.counties.filter(function (c) { return c.fips === row.fips; })[0].top_benchmark_pair;
    var close = pair && pair.close_call
      ? '<span class="badge-close">Close call</span> ' + escapeHtml(scenarioLabel(pair.leader)) + " vs " + escapeHtml(scenarioLabel(pair.trailer))
      : "Ranking holds";
    var countyName = row.name.replace(/ County$/i, "");
    countyDetail.hidden = false;
    countyDetail.innerHTML =
      "<p><strong>" + escapeHtml(countyName) + " County</strong> — " +
      scenarioLabel(scenarioId) + " " + signed(current.central) + tag("calculated") +
      ". Eligible " + integer(current.eligible) + ", feasible " + integer(current.feasible) +
      ". Envelope " + integer(env.p10) + "–" + integer(env.p90) +
      ". Zoning " + integer(current.zoning_low) + "–" + integer(current.zoning_high) +
      ". ACS ±" + integer(current.acs_moe) + ". " + close + ".</p>" +
      '<p class="coverage-bar">ADU evidence ' + pct(row.coverage.adu) +
      " · 2–6 homes " + pct(row.coverage.mm) +
      " · unknown is never zero</p>";
  }

  function renderTable() {
    var rows = docCounties().slice().sort(function (a, b) {
      return Math.abs(cell(b, scenarioId).central) - Math.abs(cell(a, scenarioId).central);
    });
    countyBody.innerHTML = rows.map(function (row) {
      var current = cell(row, scenarioId);
      var env = lockedCell(row.fips, scenarioId);
      return "<tr data-fips='" + row.fips + "' class='" + (row.fips === selectedFips ? "selected" : "") + "'>" +
        "<td>" + escapeHtml(row.name) + "</td>" +
        "<td>" + signed(current.central) + "</td>" +
        "<td>" + integer(current.eligible) + "</td>" +
        "<td>" + integer(current.feasible) + "</td>" +
        "<td>" + integer(env.p10) + "–" + integer(env.p90) + "</td>" +
        "<td>" + integer(current.zoning_low) + "–" + integer(current.zoning_high) + "</td>" +
        "<td>±" + integer(current.acs_moe) + "</td></tr>";
    }).join("");
    countyBody.querySelectorAll("tr").forEach(function (tr) {
      tr.addEventListener("click", function () {
        selectedFips = tr.getAttribute("data-fips");
        renderMap();
        renderTable();
        if (whyOpen) loadWhy();
      });
    });
  }

  function renderSliders() {
    if (!catalog) return;
    var groups = {};
    catalog.parameters.forEach(function (p) {
      groups[p.group] = groups[p.group] || [];
      groups[p.group].push(p);
    });
    sliders.innerHTML = Object.keys(groups).map(function (group) {
      var inner = groups[group].map(function (p) {
        var value = overrides.hasOwnProperty(p.name) ? overrides[p.name] : p.central;
        var step = (p.high - p.low) / 40;
        return '<div class="slider"><label><span>' + escapeHtml(p.label) + tag("assumed") +
          "</span><span>" + formatParam(p, value) + "</span></label>" +
          '<input type="range" min="' + p.low + '" max="' + p.high + '" step="' + step +
          '" value="' + value + '" data-name="' + p.name + '">' +
          '<p class="hint">' + escapeHtml(p.rationale) + "</p></div>";
      }).join("");
      return "<details class='slider-group' open><summary>" + escapeHtml(group) + "</summary>" + inner + "</details>";
    }).join("");
    sliders.querySelectorAll("input[type=range]").forEach(function (input) {
      input.addEventListener("input", function () {
        var name = input.getAttribute("data-name");
        overrides = {};
        overrides[name] = Number(input.value);
        sliders.querySelectorAll("input[type=range]").forEach(function (other) {
          if (other !== input) {
            var spec = catalog.parameters.filter(function (p) { return p.name === other.getAttribute("data-name"); })[0];
            other.value = spec.central;
          }
        });
        if (walkStep === 4) walkStep = 5;
        scheduleRecompute();
      });
    });
  }

  function formatParam(spec, value) {
    if (spec.unit === "share" || spec.unit === "probability" || spec.unit.indexOf("share") === 0) return pct(value);
    if (spec.unit.charAt(0) === "$" || spec.unit === "$ per home" || spec.unit === "$ per sq ft") return money(value);
    return Number(value).toPrecision(4);
  }

  function scheduleRecompute() {
    setStatus("Recomputing central, zoning, and ACS band…");
    clearTimeout(timer);
    timer = setTimeout(runRecompute, 280);
  }

  function runRecompute() {
    var names = Object.keys(overrides);
    if (!names.length) {
      live = null;
      envelopeNote.textContent = "Move one slider. Central values, zoning bounds, and the ACS band recompute. The p10–p90 envelope stays on the locked 200-draw run.";
      renderAll();
      if (whyOpen) loadWhy();
      setStatus("");
      return;
    }
    var id = ++requestId;
    post("/api/lab/recompute", { state: stateCode, overrides: overrides, county: selectedFips }).then(function (doc) {
      if (id !== requestId) return;
      live = doc;
      envelopeNote.textContent = doc.envelope_note;
      renderAll();
      if (whyOpen) loadWhy();
      setStatus("Live central / zoning / ACS. Envelope locked.");
    }).catch(function (err) {
      setStatus(err.message);
    });
  }

  function loadWhy() {
    if (!selectedFips) { whyBody.innerHTML = "<p>Pick a county.</p>"; return; }
    var payload = { state: stateCode, county: selectedFips, scenario: scenarioId, overrides: overrides };
    post("/api/lab/why", payload).then(function (doc) {
      whyDoc = doc;
      renderWhy();
    }).catch(function (err) {
      whyBody.innerHTML = "<p>" + escapeHtml(err.message) + "</p>";
    });
  }

  function renderWhy() {
    if (!whyDoc) return;
    var sw = docStatewide();
    var decomp = (live && live.county && live.county.package_decomposition) || whyDoc.package_decomposition;
    var wwc = locked.statewide.what_would_change;
    var inputs = whyDoc.inputs.map(function (row) {
      return '<div class="why-row"><span>' + escapeHtml(row.label) + tag(row.tag) +
        '</span><span>' + (row.id.indexOf("rent") >= 0 || row.id.indexOf("value") >= 0 || row.id === "hud_fmr_1br" ? money(row.value) : integer(row.value)) +
        (row.moe ? " ±" + integer(row.moe) : "") +
        '</span><span class="src">' + escapeHtml(row.source || "") + "</span></div>";
    }).join("");
    var assumptions = whyDoc.assumptions.map(function (row) {
      return '<div class="why-row"><span>' + escapeHtml(row.label) + tag("assumed") +
        (row.locked ? " (Handbook locked)" : "") +
        "</span><span>" + Number(row.value).toPrecision(4) + " " + escapeHtml(row.unit) + "</span><span></span></div>";
    }).join("");
    var options = whyDoc.options.map(function (row) {
      return '<div class="stat"><div class="k">' + row.option + (row.illustrative ? " · illustrative" : "") +
        "</div><div class='s'>V " + money(row.value) + " · C " + money(row.cost) +
        "</div><div class='s'>margin " + (100 * row.margin).toFixed(1) + "% · excess " +
        (100 * row.excess).toFixed(1) + "%</div></div>";
    }).join("");
    var formulas = whyDoc.formulas.map(function (row) {
      return "<article class='step'><h3>" + escapeHtml(row.label) + "</h3><p class='formula'>" +
        escapeHtml(row.formula) + "</p><p class='why'>" + escapeHtml(row.note) + "</p></article>";
    }).join("");
    var switches = (wwc && wwc.switches || []).map(function (row) {
      return "<li>" + escapeHtml(row.label) + " → " + Number(row.switch_at).toPrecision(4) +
        " " + escapeHtml(row.unit) + " (central " + Number(row.central).toPrecision(4) + ")</li>";
    }).join("");
    whyBody.innerHTML =
      "<p><strong>" + escapeHtml(whyDoc.county.name) + " · " + escapeHtml(scenarioLabel(whyDoc.scenario)) +
      "</strong> " + signed(whyDoc.result.delivery) + tag("calculated") +
      ". Host term " + signed(whyDoc.result.host_delta) + ", pipeline " + signed(whyDoc.result.pipeline_delta) + ".</p>" +
      (whyDoc.lots_note ? "<p class='help'>" + escapeHtml(whyDoc.lots_note) + "</p>" : "") +
      (whyDoc.imputed.length ? "<p class='help'>Imputed ACS fields, never zero: " + escapeHtml(whyDoc.imputed.join(", ")) + ".</p>" : "") +
      "<h3>Inputs</h3><div class='why-grid'>" + inputs + "</div>" +
      "<h3>Assumptions used</h3><div class='why-grid'>" + assumptions + "</div>" +
      "<h3>Illustrative urban detached pro forma</h3><p class='help'>" + escapeHtml(whyDoc.option_note) + "</p>" +
      "<div class='proforma'>" + options + "</div>" +
      "<h3>Formulas</h3>" + formulas +
      "<h3>Package is not a sum</h3><p>Legalization resolved " + integer(decomp.legalization_resolved) +
      " vs " + integer(decomp.legalization_if_summed) + " if summed (competition " +
      signed(decomp.competition_loss) + "). Package " + integer(decomp.package) +
      " vs sum of separate " + integer(decomp.sum_of_separate) + ".</p>" +
      "<h3>What would change the statewide conclusion</h3><p class='help'>" +
      scenarioLabel(sw.top_benchmark_pair.leader) + " vs " + scenarioLabel(sw.top_benchmark_pair.trailer) +
      ". Switching values are from the locked run.</p><ul>" + switches + "</ul>";
  }

  function renderWalk() {
    var step = WALK[walkStep];
    document.getElementById("walk-progress").textContent = "Step " + (walkStep + 1) + " of " + WALK.length + ". " + step.title;
    document.getElementById("walk-text").textContent = step.text;
  }

  function applyWalk() {
    if (walkStep === 0) { stateCode = "PA"; selectedFips = null; }
    if (walkStep >= 1) { stateCode = "PA"; scenarioId = "adu"; }
    if (walkStep >= 2) selectedFips = "42003";
    if (walkStep >= 3) { whyOpen = true; whyEl.hidden = false; document.getElementById("why-toggle").textContent = "Close the Why drawer"; }
    if (walkStep === 4 && catalog) {
      var spec = catalog.parameters.filter(function (p) { return p.name === "hazard_homeowner"; })[0];
      overrides = { hazard_homeowner: spec.low };
    }
    if (stateCode !== locked.state) { loadAll(); return; }
    renderAll();
    if (whyOpen) loadWhy();
    if (walkStep === 4) scheduleRecompute();
  }

  document.getElementById("walk-next").addEventListener("click", function () {
    walkStep = Math.min(WALK.length - 1, walkStep + 1);
    applyWalk();
  });
  document.getElementById("walk-back").addEventListener("click", function () {
    walkStep = Math.max(0, walkStep - 1);
    if (walkStep < 3) { whyOpen = false; whyEl.hidden = true; document.getElementById("why-toggle").textContent = "Open the Why drawer"; }
    if (walkStep < 4) { overrides = {}; live = null; }
    applyWalk();
  });

  document.getElementById("why-toggle").addEventListener("click", function () {
    whyOpen = !whyOpen;
    whyEl.hidden = !whyOpen;
    document.getElementById("why-toggle").textContent = whyOpen ? "Close the Why drawer" : "Open the Why drawer";
    if (whyOpen) {
      if (walkStep === 3) walkStep = 4;
      loadWhy();
      renderWalk();
    }
  });

  document.getElementById("reset").addEventListener("click", function () {
    overrides = {};
    live = null;
    envelopeNote.textContent = "Move one slider. Central values, zoning bounds, and the ACS band recompute. The p10–p90 envelope stays on the locked 200-draw run.";
    renderAll();
    if (whyOpen) loadWhy();
    setStatus("");
  });

  function download(fmt) {
    var payload = { state: stateCode, format: fmt, county: selectedFips, overrides: overrides };
    fetch("/api/lab/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (!res.ok) throw new Error("export failed");
      var name = (res.headers.get("Content-Disposition") || 'filename="lab-brief"').replace(/.*filename="?([^"]+)"?.*/, "$1");
      return res.blob().then(function (blob) { return { blob: blob, name: name }; });
    }).then(function (file) {
      var url = URL.createObjectURL(file.blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = file.name;
      link.click();
      URL.revokeObjectURL(url);
    }).catch(function (err) { setStatus(err.message); });
  }

  document.getElementById("export-md").addEventListener("click", function () {
    if (walkStep === 5) renderWalk();
    download("md");
  });
  document.getElementById("export-html").addEventListener("click", function () { download("html"); });
  document.getElementById("export-csv").addEventListener("click", function () { download("csv"); });

  loadAll();
})();
