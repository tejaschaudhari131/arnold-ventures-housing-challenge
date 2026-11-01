/* Small Homes Policy Lab client. Locked results load first. One slider
   recomputes central, zoning, and ACS MOE; the envelope stays locked. */
(function () {
  "use strict";

  var ORDER = ["adu", "missing_middle", "parking", "fees", "package", "approval"];
  var BENCHMARKS = ["adu", "missing_middle", "parking", "fees"];
  var WALK = [
    { title: "Pennsylvania is loaded", text: "All 67 counties and four Handbook scenarios are already computed. Baseline is 111,313 five-year completions. Unknown zoning is a prior, never zero." },
    { title: "Pick a reform", text: "Start with ADUs: one detached or semi-detached ADU of at least 600 sq ft, no added parking." },
    { title: "Open Allegheny County", text: "Allegheny is the walkthrough. Pittsburgh's October 2026 ADU ordinance is observed; the rest of the county is unknown." },
    { title: "Why this result?", text: "Every input is tagged observed, assumed, or calculated. The ADU pro forma is illustrative." },
    { title: "Change one assumption", text: "Move the homeowner uptake hazard. Central, zoning, and ACS MOE recompute. The p10–p90 envelope does not." },
    { title: "Export a brief", text: "Download Markdown, HTML, or a county CSV. The brief states the ranking, the close call, and what would change it." }
  ];
  var TIPS = {
    "pro forma": "A simple cost-and-value worksheet for one building type.",
    "uptake hazard": "The yearly chance a feasible lot actually starts a project.",
    "prior": "A published guess used when a local rule has not been read.",
    Envelope: "The likely range from 2,000 test runs of the published assumptions.",
    Zoning: "How the answer moves if unknown local rules are more or less strict.",
    "ACS MOE": "Census survey error on the counts and prices that feed the model."
  };

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
  var extraCards = document.getElementById("extra-cards");
  var mapStage = document.getElementById("map-stage");
  var mapTitle = document.getElementById("map-title");
  var countyDetail = document.getElementById("county-detail");
  var countyBody = document.getElementById("county-body");
  var countySelect = document.getElementById("county-select");
  var sliders = document.getElementById("sliders");
  var whyEl = document.getElementById("why");
  var whyBody = document.getElementById("why-body");
  var whyToggle = document.getElementById("why-toggle");
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

  function jargon(term, text) {
    var tip = TIPS[term] || "";
    return '<abbr title="' + escapeHtml(tip) + '">' + escapeHtml(text || term) + "</abbr>";
  }

  function tag(kind) {
    return '<abbr class="tag ' + kind + '" title="' + kind + '">' + kind + "</abbr>";
  }

  function scenarioLabel(sid) {
    var row = (locked && locked.scenarios || []).filter(function (s) { return s.id === sid; })[0];
    var raw = row ? row.short : sid;
    return String(raw).replace(/^\d+\.\s*/, "");
  }

  function cardTitle(row) {
    return String(row.label || row.short || row.id).replace(/^\d+\.\s*/, "");
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
    renderCountySelect();
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

  function rankingBadge(pair) {
    var threshold = (locked && locked.close_call_flip_share_label) || "close-call threshold";
    if (!pair || !pair.close_call) {
      return '<span class="badge-holds">Ranking holds</span>';
    }
    var keep = pair.flip_share != null ? Math.max(1, Math.round((1 - pair.flip_share) * 5)) : 4;
    return '<span class="badge-close" title="The top two Handbook reforms are close enough that a different published assumption can swap them. The ' +
      escapeHtml(threshold) + ' is 10 percent of draws.">Ranking is close: ' +
      escapeHtml(scenarioLabel(pair.leader)) + " beat " + escapeHtml(scenarioLabel(pair.trailer)) +
      " in about " + keep + " of 5 test runs.</span>";
  }

  function renderHeadline() {
    var sw = docStatewide();
    var row = sw.results[scenarioId] || sw.results.adu;
    var env = locked.statewide.results[scenarioId] || locked.statewide.results.adu;
    var pair = sw.top_benchmark_pair;
    var cover = (live && live.coverage) || locked.coverage;
    var leader = (sw.benchmark_ranking || BENCHMARKS)[0];
    var leadRow = sw.results[leader];
    var pack = sw.results.package;
    var answer = "In " + locked.name + " over 2027–2031, " + scenarioLabel(leader) +
      " adds the most (" + signed(leadRow.central) + "). All four reforms together add " +
      signed(pack.central) + " on top of " + integer(sw.results.baseline.central) + " expected.";
    headline.innerHTML =
      '<p class="headline-answer">' + escapeHtml(answer) + tag("calculated") + "</p>" +
      stat("Selected increment", signed(row.central), "calculated") +
      stat("Eligible capacity", integer(row.eligible), "calculated") +
      stat("Feasible capacity", integer(row.feasible), "calculated") +
      stat("Baseline", integer(sw.results.baseline.central), "calculated") +
      '<div class="stat"><div class="k">Uncertainty (kept separate)</div>' +
      "<div class='s'>" + jargon("Envelope") + " " + integer(env.p10) + "–" + integer(env.p90) + tag("calculated") + "</div>" +
      "<div class='s'>" + jargon("Zoning") + " " + integer(row.zoning_low) + "–" + integer(row.zoning_high) + tag("calculated") + "</div>" +
      "<div class='s'>" + jargon("ACS MOE") + " ±" + integer(row.acs_moe) + tag("observed") + "</div></div>" +
      '<div class="stat"><div class="k">Coverage and ranking</div>' +
      "<div class='s'>ADU evidence " + pct(cover.adu) + tag("calculated") +
      " · 2–6 homes " + pct(cover.mm) + tag("calculated") + "</div>" +
      "<div class='s'>" + rankingBadge(pair) + "</div>" +
      "<div class='s'>" + escapeHtml((sw.benchmark_ranking || []).map(scenarioLabel).join(" > ")) + "</div></div>";
  }

  function stat(label, value, kind) {
    return '<div class="stat"><div class="k">' + escapeHtml(label) + "</div>" +
      '<div class="v">' + value + tag(kind) + "</div></div>";
  }

  function cardHtml(s) {
    var row = docStatewide().results[s.id];
    var extra = s.kind === "extra" ? '<span class="pill t2">extra</span>' : '<span class="pill t1">benchmark</span>';
    var note = "";
    if (s.id === "package") {
      var decomp = docStatewide().package_decomposition || locked.statewide.package_decomposition;
      note = "<p class='plain'>The package is not the sum of the four reforms. Each lot takes one best option. Package " +
        signed(decomp.package) + " versus sum of separate " + signed(decomp.sum_of_separate) + tag("calculated") + ".</p>";
    }
    return '<article class="scenario-card' + (s.id === scenarioId ? " selected" : "") +
      '" data-sid="' + s.id + '"><div class="card-top"><h3><button type="button" data-sid="' + s.id +
      '">' + escapeHtml(cardTitle(s)) + "</button></h3>" + extra +
      "</div><p class='plain'>" + signed(row.central) + " vs Baseline" + tag("calculated") + "</p>" + note + "</article>";
  }

  function bindCard(root) {
    root.querySelectorAll("[data-sid]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        scenarioId = btn.getAttribute("data-sid");
        if (walkStep === 1) walkStep = 2;
        renderAll();
        if (whyOpen) loadWhy();
      });
    });
  }

  function renderCards() {
    var rows = locked.scenarios || [];
    var benches = rows.filter(function (s) { return s.id !== "baseline" && BENCHMARKS.indexOf(s.id) >= 0; });
    var extras = rows.filter(function (s) { return s.id === "package" || s.id === "approval"; });
    cards.innerHTML = benches.map(cardHtml).join("");
    extraCards.innerHTML = extras.map(cardHtml).join("");
    bindCard(cards);
    bindCard(extraCards);
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

  function bindRoving(container, selector) {
    var nodes = Array.prototype.slice.call(container.querySelectorAll(selector));
    nodes.forEach(function (node, index) {
      node.tabIndex = index === 0 ? 0 : -1;
      node.addEventListener("keydown", function (event) {
        var next = index;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % nodes.length;
        else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index - 1 + nodes.length) % nodes.length;
        else return;
        event.preventDefault();
        nodes[index].tabIndex = -1;
        nodes[next].tabIndex = 0;
        nodes[next].focus();
      });
    });
  }

  function chooseCounty(fips) {
    selectedFips = fips;
    if (walkStep === 2) walkStep = 3;
    renderMap();
    renderTable();
    renderCountySelect();
    renderHeadline();
    if (whyOpen) loadWhy();
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
      var label = escapeHtml(c.name) + " " + signed(value) + " calculated";
      return '<path class="county' + (selected ? " selected" : "") + '" role="img" data-fips="' +
        c.fips + '" d="' + d + '" fill="' + colorFor(value, maxAbs) + '"><title>' +
        label + "</title></path>";
    }).join("");
    mapStage.innerHTML = '<svg viewBox="0 0 ' + width + " " + height +
      '" role="group" aria-label="County map colored by the selected scenario">' +
      '<rect width="100%" height="100%" fill="#f7f3ea"></rect>' + paths + "</svg>";
    mapStage.querySelectorAll("[data-fips]").forEach(function (node) {
      function choose() { chooseCounty(node.getAttribute("data-fips")); }
      node.addEventListener("click", choose);
      node.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); }
      });
    });
    bindRoving(mapStage, "[data-fips]");
    renderCountyDetail();
  }

  function renderCountySelect() {
    if (!countySelect || !locked) return;
    countySelect.innerHTML = docCounties().map(function (row) {
      return '<option value="' + row.fips + '"' + (row.fips === selectedFips ? " selected" : "") +
        ">" + escapeHtml(row.name) + "</option>";
    }).join("");
  }

  function renderCountyDetail() {
    var row = selectedFips ? countyRow(selectedFips) : null;
    if (!row) { countyDetail.hidden = true; return; }
    var current = cell(row, scenarioId);
    var env = lockedCell(row.fips, scenarioId);
    var pair = row.top_benchmark_pair || locked.counties.filter(function (c) { return c.fips === row.fips; })[0].top_benchmark_pair;
    var countyName = row.name.replace(/ County$/i, "");
    countyDetail.hidden = false;
    countyDetail.innerHTML =
      "<p><strong>" + escapeHtml(countyName) + " County</strong> — " +
      scenarioLabel(scenarioId) + " " + signed(current.central) + tag("calculated") +
      ". Eligible " + integer(current.eligible) + tag("calculated") +
      ", feasible " + integer(current.feasible) + tag("calculated") +
      ". " + jargon("Envelope") + " " + integer(env.p10) + "–" + integer(env.p90) + tag("calculated") +
      ". " + jargon("Zoning") + " " + integer(current.zoning_low) + "–" + integer(current.zoning_high) + tag("calculated") +
      ". " + jargon("ACS MOE") + " ±" + integer(current.acs_moe) + tag("observed") +
      ". " + rankingBadge(pair) + ".</p>" +
      '<p class="coverage-bar">ADU evidence ' + pct(row.coverage.adu) + tag("calculated") +
      " · 2–6 homes " + pct(row.coverage.mm) + tag("calculated") +
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
        chooseCounty(tr.getAttribute("data-fips"));
      });
    });
  }

  function sliderValueText(spec, value) {
    if (spec.unit === "share" || spec.unit === "probability" || spec.unit.indexOf("share") === 0) return pct(value);
    if (spec.unit.charAt(0) === "$" || spec.unit === "$ per home" || spec.unit === "$ per sq ft") return money(value);
    if (spec.unit === "per year") return pct(value) + " a year";
    var n = Number(value);
    if (Math.abs(n) >= 1000) return integer(n);
    if (Math.abs(n) >= 1) return String(Math.round(n * 100) / 100);
    return String(Math.round(n * 10000) / 10000);
  }

  function formatParam(spec, value) {
    return sliderValueText(spec, value);
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
        var id = "lab-slider-" + p.name;
        return '<div class="slider"><label for="' + id + '"><span>' + escapeHtml(p.label) + tag("assumed") +
          "</span><span>" + formatParam(p, value) + "</span></label>" +
          '<input id="' + id + '" type="range" min="' + p.low + '" max="' + p.high + '" step="' + step +
          '" value="' + value + '" data-name="' + p.name +
          '" aria-valuetext="' + escapeHtml(sliderValueText(p, value)) + '">' +
          '<p class="hint">' + escapeHtml(p.rationale) + "</p></div>";
      }).join("");
      return "<details class='slider-group' open><summary>" + escapeHtml(group) + "</summary>" + inner + "</details>";
    }).join("");
    sliders.querySelectorAll("input[type=range]").forEach(function (input) {
      input.addEventListener("input", function () {
        var name = input.getAttribute("data-name");
        var spec = catalog.parameters.filter(function (p) { return p.name === name; })[0];
        overrides = {};
        overrides[name] = Number(input.value);
        input.setAttribute("aria-valuetext", sliderValueText(spec, Number(input.value)));
        sliders.querySelectorAll("input[type=range]").forEach(function (other) {
          if (other !== input) {
            var otherSpec = catalog.parameters.filter(function (p) { return p.name === other.getAttribute("data-name"); })[0];
            other.value = otherSpec.central;
            other.setAttribute("aria-valuetext", sliderValueText(otherSpec, otherSpec.central));
          }
        });
        if (walkStep === 4) walkStep = 5;
        scheduleRecompute();
      });
    });
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
      envelopeNote.textContent = "Move one slider. Central values, zoning bounds, and the ACS band recompute. The p10–p90 envelope stays on the locked " + ((locked && locked.draws) ? Number(locked.draws).toLocaleString("en-US") : "2,000") + "-draw run.";
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

  function setWhy(open) {
    whyOpen = open;
    whyEl.hidden = !open;
    whyToggle.setAttribute("aria-expanded", open ? "true" : "false");
    whyToggle.textContent = open ? "Close the Why drawer" : "Open the Why drawer";
    if (open) {
      if (walkStep === 3) walkStep = 4;
      loadWhy();
      renderWalk();
      whyEl.focus();
    } else {
      whyToggle.focus();
    }
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
        "</span><span>" + formatParam({ unit: row.unit }, row.value) + " " + escapeHtml(row.unit) +
        '</span><span class="src">' + escapeHtml(row.rationale || "") + "</span></div>";
    }).join("");
    var options = whyDoc.options.map(function (row) {
      return '<div class="stat"><div class="k">' + row.option + (row.illustrative ? " · illustrative" : "") +
        tag("calculated") + "</div><div class='s'>V " + money(row.value) + " · C " + money(row.cost) +
        "</div><div class='s'>margin " + (100 * row.margin).toFixed(1) + "% · excess " +
        (100 * row.excess).toFixed(1) + "%</div></div>";
    }).join("");
    var formulas = whyDoc.formulas.map(function (row) {
      return "<article class='step'><h3>" + escapeHtml(row.label) + "</h3><p class='formula'>" +
        escapeHtml(row.formula) + "</p><p class='why'>" + escapeHtml(row.note) + "</p></article>";
    }).join("");
    var switches = (wwc && wwc.switches || []).map(function (row) {
      return "<li>" + escapeHtml(row.label) + " → " + formatParam({ unit: row.unit }, row.switch_at) +
        " " + escapeHtml(row.unit) + " (central " + formatParam({ unit: row.unit }, row.central) + ")</li>";
    }).join("");
    whyBody.innerHTML =
      "<p><strong>" + escapeHtml(whyDoc.county.name) + " · " + escapeHtml(scenarioLabel(whyDoc.scenario)) +
      "</strong> " + signed(whyDoc.result.delivery) + tag("calculated") +
      ". Host term " + signed(whyDoc.result.host_delta) + ", pipeline " + signed(whyDoc.result.pipeline_delta) + ".</p>" +
      (whyDoc.lots_note ? "<p class='help'>" + escapeHtml(whyDoc.lots_note) + "</p>" : "") +
      (whyDoc.imputed.length ? "<p class='help'>Imputed ACS fields, never zero: " + escapeHtml(whyDoc.imputed.join(", ")) + ".</p>" : "") +
      "<h3>Inputs</h3><div class='why-grid'>" + inputs + "</div>" +
      "<h3>Assumptions used</h3><div class='why-grid'>" + assumptions + "</div>" +
      "<h3>Illustrative urban detached " + jargon("pro forma") + "</h3><p class='help'>" + escapeHtml(whyDoc.option_note) + "</p>" +
      "<div class='proforma'>" + options + "</div>" +
      "<h3>Formulas</h3>" + formulas +
      "<h3>Package is not a sum</h3><p>Legalization resolved " + integer(decomp.legalization_resolved) + tag("calculated") +
      " vs " + integer(decomp.legalization_if_summed) + " if summed (competition " +
      signed(decomp.competition_loss) + "). Package " + integer(decomp.package) +
      " vs sum of separate " + integer(decomp.sum_of_separate) + tag("calculated") + ".</p>" +
      "<h3>What would change the statewide conclusion</h3><p class='help'>" +
      scenarioLabel(sw.top_benchmark_pair.leader) + " vs " + scenarioLabel(sw.top_benchmark_pair.trailer) +
      ". Switching values are from the locked run. The " +
      escapeHtml((locked && locked.close_call_flip_share_label) || "close-call threshold") +
      " is 10 percent of draws.</p><ul>" + switches + "</ul>";
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
    if (walkStep >= 3) setWhy(true);
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
    if (walkStep < 3) setWhy(false);
    if (walkStep < 4) { overrides = {}; live = null; }
    applyWalk();
  });

  whyToggle.addEventListener("click", function () {
    setWhy(!whyOpen);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && whyOpen) {
      event.preventDefault();
      setWhy(false);
    }
  });

  if (countySelect) {
    countySelect.addEventListener("change", function () {
      chooseCounty(countySelect.value);
    });
  }

  document.getElementById("reset").addEventListener("click", function () {
    overrides = {};
    live = null;
    envelopeNote.textContent = "Move one slider. Central values, zoning bounds, and the ACS band recompute. The p10–p90 envelope stays on the locked " + ((locked && locked.draws) ? Number(locked.draws).toLocaleString("en-US") : "2,000") + "-draw run.";
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
