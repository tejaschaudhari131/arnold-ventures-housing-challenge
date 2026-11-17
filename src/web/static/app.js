/* Stateframe client. Recalculates by calling the equation server.
   Nothing on this page stores a precomputed grid. */
(function () {
  "use strict";

  var ORDER = ["baseline", "adu", "missing_middle", "tod", "parking", "fees", "combined"];
  var REFORMS = ["adu", "missing_middle", "tod", "parking", "fees"];
  var REFORM_LABELS = {
    adu: "ADUs",
    missing_middle: "Missing middle",
    tod: "Transit-oriented density",
    parking: "Parking reform",
    fees: "Fee reduction",
  };
  var LEGEND = {
    observed: "Measured in a public dataset from the official data list and stored for this place.",
    assumed: "A published assumption or an imputation. It is not a measurement for this place.",
    calculated: "Arithmetic in src/model/equations.py, using observed inputs and published assumptions.",
  };
  var stateCode = "PA";
  var scenarioId = "adu";
  var parameters = [];
  var overrides = {};
  var reformOn = { adu: true, missing_middle: true, tod: true, parking: true, fees: true };
  (function readEntry() {
    var q = new URLSearchParams(location.search);
    var st = (q.get("st") || "").toUpperCase();
    if (st) stateCode = st;
    if (q.has("on")) {
      var raw = q.get("on") || "";
      REFORMS.forEach(function (id) { reformOn[id] = false; });
      if (raw && raw !== "none") {
        raw.split(",").forEach(function (part) {
          var id = part === "mm" ? "missing_middle" : part;
          if (REFORMS.indexOf(id) >= 0) reformOn[id] = true;
        });
      }
    }
  })();
  var reformWeight = { adu: 1, missing_middle: 1, tod: 1, parking: 1, fees: 1 };
  var result = null;
  var mapDoc = null;
  var mapScope = "state";
  var selectedFips = null;
  var lastBand = null;
  var heroBand = null;
  var heroBandLoading = false;
  var bandRequestId = 0;
  var caseStudy = null;
  var caseStep = 0;
  var timer = null;
  var requestId = 0;
  var aduCompare = null;
  var aduCompareCache = {};
  var coreMapMetric = "homes";
  var corePinned = null;

  var statusEl = document.getElementById("status");
  var stateList = document.getElementById("state-list");
  var headline = document.getElementById("headline");
  var cards = document.getElementById("cards");
  var compareBody = document.querySelector("#compare-table tbody");
  var drivers = document.getElementById("drivers");
  var mathFocus = document.getElementById("math-focus");
  var mathSteps = document.getElementById("math-steps");
  var band = document.getElementById("band");
  var tornado = document.getElementById("tornado");
  var countyBody = document.querySelector("#county-table tbody");
  var crossOut = document.getElementById("cross-out");
  var limits = document.getElementById("limits");
  var sliders = document.getElementById("sliders");
  var reformMix = document.getElementById("reform-mix");
  var mapStage = document.getElementById("map-stage");
  var mapTitle = document.getElementById("map-title");
  var countyDetail = document.getElementById("county-detail");
  var briefEl = document.getElementById("brief");
  var caseBody = document.getElementById("case-body");
  var caseProgress = document.getElementById("case-progress");

  function setStatus(text) {
    statusEl.textContent = text || "";
  }

  function integer(value) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    return Math.round(n).toLocaleString("en-US");
  }

  function oneDecimal(value) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    if (Object.is(n, -0)) n = 0;
    var text = n.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 0 });
    if (text === "-0" || text === "−0") return "0";
    return text;
  }

  function unitSuffix(unit) {
    var map = {
      usd: "$",
      usd_per_sqft: "$/sq ft",
      per_year: "/yr",
      sqft: "sq ft",
      share: "",
      ratio: "",
      rate: "",
      elasticity: "",
      stdev: "sd",
      margin: "",
      per_margin: "",
      far: "FAR",
      miles: "mi",
      units: "",
    };
    if (!unit) return "";
    if (Object.prototype.hasOwnProperty.call(map, unit)) {
      return map[unit] ? " " + map[unit] : "";
    }
    return " " + String(unit).replace(/_/g, " ");
  }

  function permitVintageText(meta) {
    var vintage = meta && meta.permit_vintage;
    return vintage ? String(vintage) : "—";
  }

  function formatBand(low, high, spec) {
    var a = Number(low);
    var b = Number(high);
    if (!isFinite(a) || !isFinite(b)) return "—";
    var left = oneDecimal(a);
    var right = oneDecimal(b);
    if (left === "—" || right === "—") return "—";
    if (left === "0" && right === "0") {
      var label = (spec && spec.label) || "";
      var name = (spec && spec.name) || "";
      if (name === "permit_growth_rate" || /trend/i.test(label)) return "0 (no trend)";
      return "0";
    }
    return left + " to " + right;
  }

  function formatSetting(spec, value) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    var step = Number(stepFor(spec));
    var digits = 0;
    if (step > 0 && step < 1) {
      digits = Math.min(3, Math.ceil(-Math.log10(step)));
    }
    if (Math.abs(n) < 10 && Math.abs(n - Math.round(n)) > 1e-8) {
      digits = Math.min(3, Math.max(digits, 2));
    }
    var body = n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    return body + unitSuffix(spec.unit);
  }

  function signedPercent(value) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    var body = n.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
    return (n > 0 ? "+" : "") + body + "%";
  }

  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function badge(tag) {
    var key = tag === "observed" || tag === "assumed" || tag === "calculated" ? tag : "calculated";
    return '<abbr class="tag ' + key + '" title="' + escapeHtml(LEGEND[key]) + '">' + key + "</abbr>";
  }

  function tagged(value, tag, formatter) {
    return '<span class="num">' + formatter(value) + badge(tag) + "</span>";
  }

  function tagOf(node, key, fallback) {
    if (node && node.provenance && node.provenance[key]) return node.provenance[key];
    return fallback || "calculated";
  }

  async function request(path, options) {
    var response = await fetch(path, options);
    var data = {};
    var type = response.headers.get("Content-Type") || "";
    if (type.indexOf("application/json") !== -1) {
      data = await response.json();
    }
    if (!response.ok) {
      throw new Error(data.error || ("Request failed (" + response.status + ")"));
    }
    return data;
  }

  function post(path, payload) {
    return request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  function reformsPayload() {
    var out = {};
    REFORMS.forEach(function (id) {
      out[id] = { on: !!reformOn[id], weight: Number(reformWeight[id]) };
    });
    return out;
  }

  function renderStates(catalog) {
    stateList.innerHTML = "";
    catalog.forEach(function (state) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "state-btn" + (state.code === stateCode ? " active" : "");
      button.setAttribute("aria-pressed", state.code === stateCode ? "true" : "false");
      var score = Math.round(Number(state.completeness) * 100);
      button.innerHTML =
        "<strong>" + escapeHtml(state.name) + "</strong>" +
        '<span class="pill ' + (state.tier === 1 ? "t1" : "t2") + '">Tier ' + state.tier + "</span>" +
        "<span>" + integer(state.housing_units) + " homes " + badge("observed") +
        " · completeness " + score + "% " + badge("calculated") +
        (state.permit_vintage ? " · Permit data " + escapeHtml(state.permit_vintage) + " " + badge("observed") : "") +
        "</span>" +
        '<span class="meter" aria-hidden="true"><i style="width:' + score + '%"></i></span>';
      button.addEventListener("click", function () {
        mapScope = "state";
        selectedFips = null;
        selectState(state.code);
      });
      stateList.appendChild(button);
    });
  }

  function sliderValue(spec) {
    if (Object.prototype.hasOwnProperty.call(overrides, spec.name)) {
      return Number(overrides[spec.name]);
    }
    return Number(spec.central);
  }

  var CORE_PRESETS = [
    {
      id: "default",
      label: "Full 5-Reform Package",
      desc: "All five state reforms on at 100% weight and published central assumptions.",
      weights: { adu: 1, missing_middle: 1, tod: 1, parking: 1, fees: 1 },
      bounds: {}
    },
    {
      id: "high_adu_fee",
      label: "High ADU Impact Fees ($20k)",
      desc: "Raises ADU per-home fee to top of published band ($20,000) to test fee sensitivity.",
      weights: { adu: 1, missing_middle: 1, tod: 1, parking: 1, fees: 1 },
      bounds: { adu_fee_per_unit: "high" }
    },
    {
      id: "compromise",
      label: "Committee 50%-Weight Compromise",
      desc: "Full ADU and fee reform; 50% partial implementation on middle housing, TOD, and parking.",
      weights: { adu: 1, missing_middle: 0.5, tod: 0.5, parking: 0.5, fees: 1 },
      bounds: {}
    },
    {
      id: "fast_track",
      label: "Fast-Track / Low Cap-Rate",
      desc: "Lower financing cap rate, lower ADU hard cost, and upper-band ADU adoption.",
      weights: { adu: 1, missing_middle: 1, tod: 1, parking: 1, fees: 1 },
      bounds: { cap_rate: "low", adu_cost_psf: "low", adu_hazard0: "high" }
    }
  ];

  function findCoreSpec(name) {
    for (var i = 0; i < parameters.length; i += 1) {
      if (parameters[i].name === name) return parameters[i];
    }
    return null;
  }

  function applyCorePreset(presetId) {
    var preset = CORE_PRESETS.filter(function (p) { return p.id === presetId; })[0] || CORE_PRESETS[0];
    REFORMS.forEach(function (id) {
      var w = Object.prototype.hasOwnProperty.call(preset.weights, id) ? Number(preset.weights[id]) : 1;
      reformOn[id] = w > 0;
      reformWeight[id] = w > 0 ? w : 1;
    });
    overrides = {};
    Object.keys(preset.bounds).forEach(function (name) {
      var spec = findCoreSpec(name);
      var key = preset.bounds[name];
      if (spec && isFinite(Number(spec[key]))) {
        overrides[name] = Number(spec[key]);
      }
    });
    renderReformMix();
    renderSliders();
    schedule();
  }

  function renderCorePresets() {
    var box = document.getElementById("core-presets");
    if (!box) return;
    box.innerHTML =
      '<p class="aside-label">Committee amendment presets</p>' +
      '<p class="hint">Load a common bill configuration inside published assumption bands.</p>' +
      '<div class="preset-grid">' +
      CORE_PRESETS.map(function (p) {
        return '<button type="button" class="preset-btn" data-core-preset="' + escapeHtml(p.id) +
          '" title="' + escapeHtml(p.desc) + '">' + escapeHtml(p.label) + "</button>";
      }).join("") +
      "</div>";
    box.querySelectorAll("[data-core-preset]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        applyCorePreset(btn.getAttribute("data-core-preset"));
      });
    });
  }

  function pinCoreCurrent() {
    if (!result) return;
    var activeCount = REFORMS.filter(function (id) { return !!reformOn[id]; }).length;
    var ovCount = Object.keys(overrides).length;
    var label = activeCount + " of 5 reforms" + (ovCount ? " (" + ovCount + " custom)" : "");
    var byCounty = {};
    (result.counties || []).forEach(function (c) {
      byCounty[c.fips] = Number(c.combined) || 0;
    });
    corePinned = {
      state: stateCode,
      label: label,
      packageNet: Number(result.scenarios.combined.incremental_completions) || 0,
      byCounty: byCounty
    };
    renderCorePin();
  }

  function renderCorePin() {
    var box = document.getElementById("core-pin");
    if (!box || !result) return;
    if (!corePinned || corePinned.state !== stateCode) {
      box.innerHTML =
        '<div class="pin-head"><span class="aside-label">Compare bills (A vs. B)</span>' +
        '<button type="button" class="pin-act" id="core-pin-save">Pin current as A</button></div>' +
        '<p class="hint">Pin this package, then adjust weights or sliders to compare Bill B against Bill A.</p>';
      var saveBtn = box.querySelector("#core-pin-save");
      if (saveBtn) saveBtn.addEventListener("click", pinCoreCurrent);
      return;
    }
    var curPkg = Number(result.scenarios.combined.incremental_completions) || 0;
    var dPkg = curPkg - corePinned.packageNet;
    var cObj = selectedFips ? countyByFips(selectedFips) : null;
    var curC = cObj ? (Number(cObj.combined) || 0) : 0;
    var pinC = (cObj && Object.prototype.hasOwnProperty.call(corePinned.byCounty, cObj.fips)) ? corePinned.byCounty[cObj.fips] : 0;
    var dC = curC - pinC;
    var diffStr = (dPkg > 0 ? "+" : "") + integer(dPkg);
    var cDiffStr = (dC > 0 ? "+" : "") + integer(dC);
    box.innerHTML =
      '<div class="pin-head"><span class="aside-label">Pinned A vs. Current B</span>' +
      '<span class="pin-btns"><button type="button" class="pin-act" id="core-pin-update">Re-pin</button>' +
      '<button type="button" class="pin-act" id="core-pin-clear">Clear</button></span></div>' +
      '<p class="hint">Pinned A: <strong>' + escapeHtml(corePinned.label) + "</strong></p>" +
      '<table class="pin-table" aria-label="Pinned package A versus current package B">' +
      "<thead><tr><th>Scope (Package)</th><th>Pinned A</th><th>Current B</th><th>Diff (B−A)</th></tr></thead><tbody>" +
      "<tr><td>" + escapeHtml(stateCode) + " net new</td><td>" + integer(corePinned.packageNet) + "</td><td>" +
      integer(curPkg) + "</td><td><strong>" + diffStr + "</strong></td></tr>" +
      (cObj
        ? "<tr><td>" + escapeHtml(cObj.name) + "</td><td>" + integer(pinC) + "</td><td>" +
          integer(curC) + "</td><td><strong>" + cDiffStr + "</strong></td></tr>"
        : "") +
      "</tbody></table>";
    var upBtn = box.querySelector("#core-pin-update");
    var clBtn = box.querySelector("#core-pin-clear");
    if (upBtn) upBtn.addEventListener("click", pinCoreCurrent);
    if (clBtn) clBtn.addEventListener("click", function () { corePinned = null; renderCorePin(); });
  }

  function renderReformMix() {
    reformMix.innerHTML = "";
    var wrap = document.createElement("div");
    wrap.className = "reform-mix";
    var title = document.createElement("p");
    title.className = "aside-label";
    title.textContent = "Reform mix";
    wrap.appendChild(title);
    var hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "Turn a reform off, or give it a weight below 100 percent, to see the combined package without that piece. Standalone cards stay visible so the before-and-after is still readable.";
    wrap.appendChild(hint);
    REFORMS.forEach(function (id) {
      var row = document.createElement("div");
      row.className = "reform-row";
      var label = document.createElement("label");
      label.className = "switch";
      var box = document.createElement("input");
      box.type = "checkbox";
      box.checked = !!reformOn[id];
      box.setAttribute("aria-label", "Include " + REFORM_LABELS[id] + " in the package");
      label.appendChild(box);
      label.appendChild(document.createTextNode(REFORM_LABELS[id]));
      var value = document.createElement("span");
      value.textContent = Math.round(reformWeight[id] * 100) + "%";
      var range = document.createElement("input");
      range.type = "range";
      range.min = "0";
      range.max = "1";
      range.step = "0.05";
      range.value = String(reformWeight[id]);
      range.disabled = !reformOn[id];
      range.setAttribute("aria-label", REFORM_LABELS[id] + " weight in the package");
      box.addEventListener("change", function () {
        reformOn[id] = box.checked;
        range.disabled = !box.checked;
        schedule();
      });
      range.addEventListener("input", function () {
        reformWeight[id] = Number(range.value);
        value.textContent = Math.round(reformWeight[id] * 100) + "%";
        schedule();
      });
      row.appendChild(label);
      row.appendChild(value);
      row.appendChild(range);
      wrap.appendChild(row);
    });
    reformMix.appendChild(wrap);
  }

  function renderSliders() {
    var groups = {};
    var order = [];
    parameters.forEach(function (spec) {
      if (!groups[spec.group]) {
        groups[spec.group] = [];
        order.push(spec.group);
      }
      groups[spec.group].push(spec);
    });
    sliders.innerHTML = "";
    order.forEach(function (group, index) {
      var details = document.createElement("details");
      details.className = "slider-group";
      if (index < 2) details.open = true;
      var summary = document.createElement("summary");
      summary.textContent = group;
      details.appendChild(summary);
      groups[group].forEach(function (spec) {
        var item = document.createElement("div");
        item.className = "slider";
        var label = document.createElement("label");
        var sliderId = "core-slider-" + spec.name;
        label.setAttribute("for", sliderId);
        var title = document.createElement("span");
        title.textContent = spec.label;
        var value = document.createElement("span");
        var current = sliderValue(spec);
        value.innerHTML = escapeHtml(formatSetting(spec, current)) + badge("assumed");
        label.appendChild(title);
        label.appendChild(value);
        var input = document.createElement("input");
        input.type = "range";
        input.id = sliderId;
        input.min = spec.low;
        input.max = spec.high;
        input.step = stepFor(spec);
        input.value = String(current);
        input.setAttribute("aria-label", spec.label);
        input.setAttribute("aria-valuetext", formatSetting(spec, current));
        function onSlide() {
          var next = Number(input.value);
          value.innerHTML = escapeHtml(formatSetting(spec, next)) + badge("assumed");
          input.setAttribute("aria-valuetext", formatSetting(spec, next));
          if (Math.abs(next - Number(spec.central)) < Number(input.step) / 2) {
            delete overrides[spec.name];
          } else {
            overrides[spec.name] = next;
          }
          schedule();
        }
        input.addEventListener("input", onSlide);
        input.addEventListener("change", onSlide);
        var note = document.createElement("p");
        note.className = "hint";
        note.textContent = spec.help || ("Published band " + oneDecimal(spec.low) + " to " + oneDecimal(spec.high) + ".");
        item.appendChild(label);
        item.appendChild(input);
        item.appendChild(note);
        details.appendChild(item);
      });
      sliders.appendChild(details);
    });
  }

  function stepFor(spec) {
    var span = Number(spec.high) - Number(spec.low);
    if (!(span > 0)) return "1";
    var rough = span / 80;
    var power = Math.pow(10, Math.floor(Math.log10(rough)));
    var step = Math.round(rough / power) * power;
    if (!(step > 0)) step = power;
    return String(step);
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(function () {
      simulate().catch(fail);
    }, 150);
  }

  function renderHeadline() {
    var lift = result.scenarios.combined.lift_pct;
    var lotTag = tagOf(result, "lot_feasible_share", "assumed");
    var pack = result.scenarios.combined.incremental_completions;
    var answer = "In " + result.name + " over five years, the package adds " +
      integer(pack) + " homes on top of " + integer(result.baseline_completions_5yr) + " expected.";
    var hasRange = heroBand && isFinite(Number(heroBand.p10)) && isFinite(Number(heroBand.p90));
    var joiner = hasRange && (Number(heroBand.p10) <= 0 || Number(heroBand.p90) <= 0) ? " to " : "–";
    var rangeKicker = hasRange
      ? '<p class="range-kicker">Seeded range (10th–90th percentile, ' + integer(heroBand.draws) + " draws)</p>"
      : "";
    var rangeHero = hasRange
      ? "Likely " + integer(heroBand.p10) + joiner + integer(heroBand.p90) + " extra homes"
      : (heroBandLoading ? "Calculating likely range…" : "Likely range unavailable");
    headline.innerHTML =
      '<p class="model-badge screening">Screening model · statewide estimate · 11 states</p>' +
      rangeKicker +
      '<p class="range-hero">' + rangeHero + "</p>" +
      '<p class="middle-est">Middle estimate <span data-bind="scenarios.combined.incremental_completions">' +
      integer(pack) + '</span> extra homes, on top of <span data-bind="baseline_completions_5yr">' +
      integer(result.baseline_completions_5yr) + "</span> expected.</p>" +
      '<p>' + (window.StateframeFrame ? window.StateframeFrame.FUNNEL_UNAVAILABLE : "") + "</p>" +
      '<p class="headline-answer">' + escapeHtml(answer) + badge("calculated") + "</p>" +
      card(
        "Baseline completions",
        tagged(result.baseline_completions_5yr, tagOf(result, "baseline_completions_5yr"), integer),
        "Five-year homes completed if today's permit pace continues. This is the core baseline, calculated from observed permits and assumed completion ratios."
      ) +
      card(
        "Package, net new",
        tagged(pack, "calculated", integer),
        signedPercent(lift) + " versus baseline. The package is not the sum of the five reforms. Overlap among the reforms that are switched on is removed."
      ) +
      card(
        "Walkshed",
        tagged(result.walkshed_sqmi, tagOf(result, "walkshed_sqmi"), function (value) { return oneDecimal(value) + " sq mi"; }),
        "Calculated area around major transit stops, after an assumed overlap discount."
      ) +
      card(
        "Lot screen",
        tagged(result.lot_feasible_share, lotTag, function (value) { return Math.round(value * 100) + "%"; }),
        result.lot_feasible_note || "Share of single-family lots that can hold an extra apartment."
      );
  }

  function card(label, valueHtml, sub) {
    return '<article class="stat"><div class="k">' + escapeHtml(label) + '</div><div class="v">' + valueHtml + '</div><div class="s">' + escapeHtml(sub) + "</div></article>";
  }

  function scenarioColumn(id) {
    return id === "baseline" ? "baseline_completions" : id;
  }

  function closeCallFor(id) {
    var chosen = result.scenarios[id];
    if (chosen.close_call) return chosen.close_call_reason;
    if (lastBand && lastBand.scenario === id && lastBand.crosses_zero) {
      return "Close call: the p10–p90 band crosses zero, so the published assumption range includes both a gain and a loss.";
    }
    return "";
  }

  function renderCards() {
    cards.innerHTML = "";
    ORDER.forEach(function (id) {
      var row = result.scenarios[id];
      var article = document.createElement("article");
      var off = id !== "baseline" && id !== "combined" && !reformOn[id];
      article.className = "scenario-card" + (id === scenarioId ? " selected" : "") + (off ? " off" : "");
      var before = result.baseline_completions_5yr;
      var after = row.completions_5yr;
      var net = id === "baseline" ? 0 : row.incremental_completions;
      var close = closeCallFor(id);
      var top = document.createElement("div");
      top.className = "card-top";
      var title = document.createElement("h3");
      var titleBtn = document.createElement("button");
      titleBtn.type = "button";
      titleBtn.textContent = row.label;
      title.appendChild(titleBtn);
      top.appendChild(title);
      if (REFORMS.indexOf(id) !== -1) {
        var label = document.createElement("label");
        label.className = "switch";
        var box = document.createElement("input");
        box.type = "checkbox";
        box.checked = !!reformOn[id];
        box.setAttribute("aria-label", "Include " + row.label + " in the package");
        box.addEventListener("click", function (event) { event.stopPropagation(); });
        box.addEventListener("change", function () {
          reformOn[id] = box.checked;
          renderReformMix();
          schedule();
        });
        label.appendChild(box);
        label.appendChild(document.createTextNode("In package"));
        top.appendChild(label);
      }
      article.appendChild(top);
      if (close) {
        var flag = document.createElement("p");
        flag.innerHTML = '<span class="badge-uncertain" title="The published assumption range includes both a gain and a loss.">Outcome uncertain: under some assumptions this reform adds no homes.</span> ' +
          escapeHtml(close);
        article.appendChild(flag);
      }
      var plain = document.createElement("p");
      plain.className = "plain";
      plain.textContent = row.explanation;
      article.appendChild(plain);
      var grid = document.createElement("div");
      grid.className = "ba";
      grid.innerHTML =
        "<div><div class='k'>Before</div><div class='v'>" + tagged(before, "calculated", integer) + "</div></div>" +
        "<div><div class='k'>After</div><div class='v'>" + tagged(after, "calculated", integer) + "</div></div>" +
        "<div><div class='k'>Net new</div><div class='v'>" + tagged(net, "calculated", integer) + "</div></div>";
      article.appendChild(grid);
      titleBtn.setAttribute("aria-pressed", id === scenarioId ? "true" : "false");
      function choose() { selectScenario(id); }
      titleBtn.addEventListener("click", function (event) {
        event.stopPropagation();
        choose();
      });
      cards.appendChild(article);
    });
  }

  function renderCompare() {
    compareBody.innerHTML = "";
    ORDER.forEach(function (id) {
      var row = result.scenarios[id];
      var tr = document.createElement("tr");
      if (id === scenarioId) tr.className = "selected";
      tr.tabIndex = 0;
      tr.setAttribute("role", "button");
      tr.setAttribute("aria-pressed", id === scenarioId ? "true" : "false");
      var net = id === "baseline" ? "—" : integer(row.incremental_completions);
      var lift = id === "baseline" ? "—" : signedPercent(row.lift_pct);
      var flag = "";
      if (row.close_call || (lastBand && lastBand.scenario === id && lastBand.crosses_zero)) {
        flag = ' <span class="badge-uncertain" title="The published assumption range includes both a gain and a loss.">Outcome uncertain</span>';
      }
      var capLabel = "";
      if (id === "combined" && row.absorption_cap_binding) capLabel = " · absorption cap";
      else if (row.cap_binding) capLabel = " · capped";
      tr.innerHTML =
        "<td>" + escapeHtml(row.label) + capLabel + flag + "</td>" +
        "<td>" + tagged(row.permits_5yr, "calculated", integer) + "</td>" +
        "<td>" + tagged(row.completions_5yr, "calculated", integer) + "</td>" +
        "<td>" + (id === "baseline" ? "—" : tagged(row.incremental_completions, "calculated", integer)) + "</td>" +
        "<td>" + tagged(row.annualized_completions, "calculated", integer) + "</td>" +
        "<td>" + (id === "baseline" ? "—" : tagged(row.lift_pct, "calculated", signedPercent)) + "</td>" +
        "<td>" + escapeHtml(permitVintageText(result.meta)) + "</td>";
      void net;
      void lift;
      function choose() { selectScenario(id); }
      tr.addEventListener("click", choose);
      tr.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          choose();
        }
      });
      compareBody.appendChild(tr);
    });
    var chosen = result.scenarios[scenarioId];
    var parts = chosen.drivers.map(function (line) { return "<li>" + escapeHtml(line) + "</li>"; }).join("");
    var extra = "<p class='plain'>" + escapeHtml(chosen.explanation) + "</p>";
    if (scenarioId === "combined") {
      var c = result.components;
      extra += "<p>Inside the package: ADUs " + tagged(c.combined_adu, "calculated", integer) +
        ", missing middle " + tagged(c.combined_mm, "calculated", integer) +
        ", TOD " + tagged(c.combined_tod, "calculated", integer) +
        ", parking " + tagged(c.combined_parking, "calculated", integer) +
        ", fees " + tagged(c.combined_fees, "calculated", integer) +
        ". Those five parts add to the package total. Fee and parking savings inside the zoning pro formas can make the package larger than the sum of the five reforms run alone.</p>";
      var standaloneCap = result.scenarios.missing_middle.capacity_completions;
      if (c.combined_mm > standaloneCap) {
        extra += "<p>Package missing middle (" + tagged(c.combined_mm, "calculated", integer) +
          ") can exceed standalone missing middle (" + tagged(standaloneCap, "calculated", integer) +
          ") because the fee cut and market parking are in the package pro forma.</p>";
      }
    }
    if (scenarioId === "combined" && chosen.cap_binding) {
      extra += "<p>Uncapped potential is " + tagged(chosen.uncapped_potential, "calculated", integer) +
        " completions, before the absorption cap and the ADU stock ceiling.";
      if (chosen.absorption_cap_binding && capRoundsAboveZero(chosen.absorption_cap)) {
        extra += " The binding absorption cap is " + tagged(chosen.absorption_cap, "calculated", integer) + ".";
      }
      extra += "</p>";
    } else if (chosen.cap_binding) {
      extra += "<p>Feasible capacity is " + tagged(chosen.capacity_completions, "calculated", integer) +
        " completions. The five-year figure is the portion the absorption or adoption ceiling lets through.</p>";
    }
    if (chosen.close_call_reason) {
      extra += "<p><span class='badge-uncertain' title='The published assumption range includes both a gain and a loss.'>Outcome uncertain: under some assumptions this reform adds no homes.</span> " + escapeHtml(chosen.close_call_reason) + "</p>";
    }
    drivers.className = "callout" + (chosen.cap_binding || chosen.close_call ? " warn" : "");
    drivers.innerHTML = "<strong>" + escapeHtml(chosen.label) + "</strong><ul>" + parts + "</ul>" + extra;
    renderPackageNote();
  }

  function capRoundsAboveZero(value) {
    var n = Number(value);
    return isFinite(n) && Math.round(n) !== 0;
  }

  function renderPackageNote() {
    var note = document.getElementById("package-note");
    if (!note || !result || !result.components) return;
    var pack = result.scenarios.combined;
    var mm = result.components.combined_mm;
    var standaloneCap = result.scenarios.missing_middle.capacity_completions;
    var html = "Uncapped potential for the package is " + tagged(pack.uncapped_potential, "calculated", integer) + ".";
    if (pack.absorption_cap_binding && capRoundsAboveZero(pack.absorption_cap)) {
      html += " Where the absorption cap binds, that cap is " + tagged(pack.absorption_cap, "calculated", integer) + ".";
    }
    if (mm > standaloneCap) {
      html += " Package missing middle (" + tagged(mm, "calculated", integer) +
        ") can exceed standalone missing middle (" + tagged(standaloneCap, "calculated", integer) +
        ") because the fee cut and market parking are in the package pro forma.";
    }
    note.hidden = false;
    note.innerHTML = html;
  }

  function renderMath() {
    var chosen = result.scenarios[scenarioId];
    mathFocus.textContent = chosen.label + " in " + result.name +
      ". The steps use " + result.focus_county + " as a worked example. The last step is the official state total, the sum of every county. Each result is calculated. The tags under a step name the inputs.";
    mathSteps.innerHTML = "";
    (chosen.trace || []).forEach(function (step, index) {
      var article = document.createElement("article");
      article.className = "step";
      var resultTag = (step.provenance && step.provenance.result) || "calculated";
      var inputs = (step.inputs || []).map(function (item) {
        return "<li>" + escapeHtml(item.label) + " " + badge(item.tag) + "</li>";
      }).join("");
      article.innerHTML =
        "<h3>" + (index + 1) + ". " + escapeHtml(step.title) + "</h3>" +
        '<p class="eq">' + escapeHtml(step.equation) + "</p>" +
        '<p class="eq">' + escapeHtml(step.substitution) + "</p>" +
        '<p class="result">' + tagged(step.result, resultTag, integer) + " " + escapeHtml(step.unit) + "</p>" +
        (inputs ? "<ul>" + inputs + "</ul>" : "") +
        '<p class="why">' + escapeHtml(step.why) + "</p>";
      mathSteps.appendChild(article);
    });
  }

  function renderCounties() {
    var rows = result.counties.slice().sort(function (a, b) {
      return b.housing_units - a.housing_units;
    });
    var totals = { baseline_completions: 0, adu: 0, missing_middle: 0, tod: 0, parking: 0, fees: 0, combined: 0 };
    countyBody.innerHTML = "";
    rows.forEach(function (county) {
      Object.keys(totals).forEach(function (key) { totals[key] += county[key]; });
      var tr = document.createElement("tr");
      var valueTag = county.value_imputed ? "assumed" : "observed";
      var flag = county.close_call ? ' <span class="badge-uncertain" title="The published assumption range includes both a gain and a loss.">Outcome uncertain</span>' : "";
      tr.innerHTML =
        "<td>" + escapeHtml(county.name) + (county.value_imputed ? " *" : "") + flag + "</td>" +
        "<td>" + escapeHtml(county.context) + "</td>" +
        "<td>" + tagged(county.baseline_completions, "calculated", integer) + "</td>" +
        "<td>" + tagged(county.adu, "calculated", integer) + "</td>" +
        "<td>" + tagged(county.missing_middle, "calculated", integer) + "</td>" +
        "<td>" + tagged(county.tod, "calculated", integer) + "</td>" +
        "<td>" + tagged(county.parking, "calculated", integer) + "</td>" +
        "<td>" + tagged(county.fees, "calculated", integer) + "</td>" +
        "<td>" + tagged(county.combined, "calculated", integer) + "</td>";
      tr.title = county.name + " median value is " + valueTag + ". " + (county.close_call_reason || "");
      tr.addEventListener("click", function () {
        selectedFips = county.fips;
        mapScope = "state";
        renderMap();
      });
      countyBody.appendChild(tr);
    });
    var foot = document.createElement("tr");
    foot.innerHTML =
      "<td>Sum (equals rounded state total)</td><td></td>" +
      "<td>" + tagged(totals.baseline_completions, "calculated", integer) + "</td>" +
      "<td>" + tagged(totals.adu, "calculated", integer) + "</td>" +
      "<td>" + tagged(totals.missing_middle, "calculated", integer) + "</td>" +
      "<td>" + tagged(totals.tod, "calculated", integer) + "</td>" +
      "<td>" + tagged(totals.parking, "calculated", integer) + "</td>" +
      "<td>" + tagged(totals.fees, "calculated", integer) + "</td>" +
      "<td>" + tagged(totals.combined, "calculated", integer) + "</td>";
    countyBody.appendChild(foot);
  }

  function renderLimits() {
    limits.innerHTML = "";
    ORDER.forEach(function (id) {
      var chosen = result.scenarios[id];
      var article = document.createElement("article");
      var items = (chosen.cannot || []).map(function (line) {
        return "<li>" + escapeHtml(line) + "</li>";
      }).join("");
      article.innerHTML = "<h3>" + escapeHtml(chosen.label) + "</h3><ul>" + items + "</ul>";
      if (id === scenarioId) article.style.background = "var(--green-soft)";
      limits.appendChild(article);
    });
    var note = document.createElement("article");
    note.innerHTML = "<h3>Data for this state</h3><p>" + escapeHtml(result.lot_feasible_note || "") +
      "</p><p>" + escapeHtml(result.legal_note || "") + "</p><p>" + escapeHtml(result.transit_note || "") + "</p>";
    limits.appendChild(note);
  }

  function renderBrief() {
    var chosen = result.scenarios[scenarioId];
    var before = result.baseline_completions_5yr;
    var after = chosen.completions_5yr;
    var net = scenarioId === "baseline" ? 0 : chosen.incremental_completions;
    var assumptionRows = parameters.slice(0, 6).map(function (spec) {
      var current = sliderValue(spec);
      return "<tr><td>" + escapeHtml(spec.label) + "</td><td>" +
        escapeHtml(formatSetting(spec, current)) + badge("assumed") + "</td><td>" +
        escapeHtml(formatBand(spec.low, spec.high, spec)) + "</td></tr>";
    }).join("");
    var close = closeCallFor(scenarioId);
    briefEl.innerHTML =
      '<div class="brief-sheet">' +
      "<p class='eyebrow'>Stateframe one-page brief</p>" +
      "<h2>" + escapeHtml(result.name) + " · " + escapeHtml(chosen.label) + "</h2>" +
      "<p>" + escapeHtml(chosen.explanation) + "</p>" +
      '<div class="brief-grid">' +
      "<div><div class='k'>Before</div><div class='v'>" + tagged(before, "calculated", integer) + "</div><p>Five-year completions, current rules.</p></div>" +
      "<div><div class='k'>After</div><div class='v'>" + tagged(after, "calculated", integer) + "</div><p>Baseline plus this scenario.</p></div>" +
      "<div><div class='k'>Net new</div><div class='v'>" + tagged(net, "calculated", integer) + "</div><p>Calculated addition over five years.</p></div>" +
      "</div>" +
      (close ? "<p><span class='badge-uncertain' title='The published assumption range includes both a gain and a loss.'>Outcome uncertain: under some assumptions this reform adds no homes.</span> " + escapeHtml(close) + "</p>" : "") +
      "<h3>Assumptions in this run</h3>" +
      "<table><thead><tr><th>Assumption</th><th>Value</th><th>Published band</th></tr></thead><tbody>" +
      assumptionRows +
      "<tr><td>Lot screen</td><td>" + tagged(result.lot_feasible_share, tagOf(result, "lot_feasible_share"), function (value) { return Math.round(Number(value) * 100) + "%"; }) +
      "</td><td>" + escapeHtml(result.lot_feasible_note || "") + "</td></tr>" +
      "</tbody></table>" +
      "<h3>Provenance</h3>" +
      "<p>" + badge("observed") + " " + escapeHtml(LEGEND.observed) + "</p>" +
      "<p>" + badge("assumed") + " " + escapeHtml(LEGEND.assumed) + "</p>" +
      "<p>" + badge("calculated") + " " + escapeHtml(LEGEND.calculated) + "</p>" +
      "<p><strong>What this cannot tell you.</strong> " + escapeHtml((chosen.cannot && chosen.cannot[0]) || "") + "</p>" +
      (aduCompare ? "<p class='adu-fee-note'>" + escapeHtml(aduCompare.notes.docs) + "</p>" : "") +
      "<p>Housing stock and prices are Census ACS figures. Permits are the Building Permits Survey. The map uses Census gazetteer interior points. County integers sum to the rounded state total. Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns, Carnegie Mellon University. Apache-2.0.</p>" +
      "</div>";
  }

  function pointsFor(code) {
    if (!mapDoc || !mapDoc.points) return [];
    return mapDoc.points.filter(function (point) { return point.state === code; });
  }

  function boundsOf(points) {
    var minLat = Infinity;
    var maxLat = -Infinity;
    var minLon = Infinity;
    var maxLon = -Infinity;
    points.forEach(function (point) {
      minLat = Math.min(minLat, point.lat);
      maxLat = Math.max(maxLat, point.lat);
      minLon = Math.min(minLon, point.lon);
      maxLon = Math.max(maxLon, point.lon);
    });
    var padLat = Math.max(0.15, (maxLat - minLat) * 0.08);
    var padLon = Math.max(0.15, (maxLon - minLon) * 0.08);
    return { minLat: minLat - padLat, maxLat: maxLat + padLat, minLon: minLon - padLon, maxLon: maxLon + padLon };
  }

  function project(point, box, width, height) {
    var x = ((point.lon - box.minLon) / (box.maxLon - box.minLon)) * width;
    var y = ((box.maxLat - point.lat) / (box.maxLat - box.minLat)) * height;
    return [x, y];
  }

  function convexHull(coords) {
    var pts = coords.slice().sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
    if (pts.length < 3) return pts;
    function cross(o, a, b) {
      return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    }
    var lower = [];
    pts.forEach(function (p) {
      while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
      lower.push(p);
    });
    var upper = [];
    pts.slice().reverse().forEach(function (p) {
      while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
      upper.push(p);
    });
    upper.pop();
    lower.pop();
    return lower.concat(upper);
  }

  function countyByFips(fips) {
    if (!result) return null;
    for (var i = 0; i < result.counties.length; i += 1) {
      if (result.counties[i].fips === fips) return result.counties[i];
    }
    return null;
  }

  function metricOf(county) {
    if (!county) return 0;
    return Number(county[scenarioColumn(scenarioId)] || 0);
  }

  function colorFor(value, max) {
    var t = max > 0 ? Math.max(0, value) / max : 0;
    var r = Math.round(244 - t * 220);
    var g = Math.round(240 - t * 140);
    var b = Math.round(230 - t * 160);
    return "rgb(" + r + "," + g + "," + b + ")";
  }

  var CORE_BOTTLENECKS = {
    zoning: {
      id: "zoning",
      label: "Zoning-locked",
      color: "#0e6e5c",
      note: "Zoning reforms (ADUs, middle housing, TOD) drive the majority of potential new homes here."
    },
    fee: {
      id: "fee",
      label: "Fee-sensitive",
      color: "#d99116",
      note: "Pipeline fee and parking cost reductions account for a major share of feasible gains."
    },
    market: {
      id: "market",
      label: "Rent/cost-constrained",
      color: "#c8553d",
      note: "Local rents and home values sit close to construction costs, keeping market-rate lift modest."
    }
  };

  function coreCountyBottleneck(county) {
    if (!county) return CORE_BOTTLENECKS.market;
    var legalTop = Math.max(Number(county.adu) || 0, Number(county.missing_middle) || 0, Number(county.tod) || 0);
    var costTop = Math.max(Number(county.fees) || 0, Number(county.parking) || 0);
    var base = Number(county.baseline_completions) || 0;
    var pkg = Number(county.combined) || 0;
    var pkgLift = base > 0 ? pkg / base : 0;
    if (legalTop > costTop && pkgLift >= 0.08) return CORE_BOTTLENECKS.zoning;
    if (pkg >= 15 && (costTop >= legalTop || pkgLift >= 0.05)) return CORE_BOTTLENECKS.fee;
    return CORE_BOTTLENECKS.market;
  }

  function coreCountyLiftPct(county) {
    if (!county || scenarioId === "baseline") return 0;
    var base = Number(county.baseline_completions) || 0;
    if (base <= 0) return 0;
    return (metricOf(county) / base) * 100;
  }

  function renderCoreMapMetrics() {
    var box = document.getElementById("core-map-metrics");
    var leg = document.getElementById("core-bottleneck-legend");
    if (!box) return;
    if (mapScope === "nation") {
      box.hidden = true;
      if (leg) leg.hidden = true;
      return;
    }
    box.hidden = false;
    var modes = [
      { id: "homes", label: "Extra homes" },
      { id: "lift", label: "% Lift vs. baseline" },
      { id: "bottleneck", label: "Primary bottleneck" }
    ];
    box.innerHTML = modes.map(function (m) {
      return '<button type="button" aria-pressed="' + (coreMapMetric === m.id) + '" data-core-metric="' + m.id + '">' +
        escapeHtml(m.label) + "</button>";
    }).join("");
    box.querySelectorAll("[data-core-metric]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        coreMapMetric = btn.getAttribute("data-core-metric") || "homes";
        renderMap();
      });
    });
  }

  function renderCountyDetail(county) {
    if (!county) {
      countyDetail.hidden = true;
      countyDetail.innerHTML = "";
      return;
    }
    var valueTag = county.value_imputed ? "assumed" : "observed";
    var column = scenarioColumn(scenarioId);
    var bInfo = coreCountyBottleneck(county);
    var lift = coreCountyLiftPct(county);
    var liftText = scenarioId === "baseline" ? "baseline view" : ((lift >= 0 ? "+" : "") + lift.toFixed(1) + "% vs. baseline");
    countyDetail.hidden = false;
    countyDetail.innerHTML =
      "<strong>" + escapeHtml(county.name) + "</strong> " +
      '<span class="b-pill ' + escapeHtml(bInfo.id) + '">' + escapeHtml(bInfo.label) + "</span> " +
      (county.close_call ? '<span class="badge-uncertain" title="The published assumption range includes both a gain and a loss.">Outcome uncertain</span> ' : "") +
      "<p class='plain'>" + escapeHtml(county.name) + " rolls into " + escapeHtml(result.name) +
      " through the same county pro forma as every other county. The state total is the sum, not a separate model. " +
      (county.close_call_reason || "This county is not sitting on the feasibility hurdle.") + "</p>" +
      "<p>Homes " + tagged(county.housing_units, "observed", integer) +
      ". Median value " + tagged(county.median_value, valueTag, function (value) { return "$" + integer(value); }) +
      ". Selected scenario " + tagged(county[column], "calculated", integer) +
      " (" + escapeHtml(liftText) + ") · " + escapeHtml(bInfo.note) + "</p>";
  }

  function renderMap() {
    renderCoreMapMetrics();
    if (!mapDoc || !result) {
      mapStage.textContent = "County interior points are still loading.";
      return;
    }
    if (mapScope === "nation") renderNationMap();
    else renderStateMap();
  }

  function renderStateMap() {
    var points = pointsFor(stateCode);
    mapTitle.textContent = result.name + " counties";
    if (!points.length) {
      mapStage.textContent = "No gazetteer points for this state.";
      return;
    }
    var box = boundsOf(points);
    var width = 800;
    var height = 520;
    var maxMetric = 0;
    var bCounts = { zoning: 0, fee: 0, market: 0 };
    points.forEach(function (point) {
      var c = countyByFips(point.fips);
      var m = coreMapMetric === "lift" ? coreCountyLiftPct(c) : metricOf(c);
      maxMetric = Math.max(maxMetric, Math.abs(m));
      var b = coreCountyBottleneck(c);
      bCounts[b.id] = (bCounts[b.id] || 0) + 1;
    });
    var bLeg = document.getElementById("core-bottleneck-legend");
    if (bLeg) {
      if (coreMapMetric === "bottleneck") {
        bLeg.hidden = false;
        bLeg.innerHTML =
          '<span class="b-dot zoning"></span> Zoning-locked (' + bCounts.zoning + ") · " +
          '<span class="b-dot fee"></span> Fee-sensitive (' + bCounts.fee + ") · " +
          '<span class="b-dot market"></span> Rent/cost-constrained (' + bCounts.market + ")";
      } else if (coreMapMetric === "lift") {
        bLeg.hidden = false;
        bLeg.textContent = "Circle shade shows 5-year % lift over each county's baseline completions.";
      } else {
        bLeg.hidden = true;
        bLeg.textContent = "";
      }
    }
    var hull = convexHull(points.map(function (point) { return project(point, box, width, height); }));
    var hullPath = hull.map(function (pair, index) {
      return (index === 0 ? "M" : "L") + pair[0].toFixed(1) + " " + pair[1].toFixed(1);
    }).join(" ") + " Z";
    var circles = points.map(function (point) {
      var county = countyByFips(point.fips);
      var xy = project(point, box, width, height);
      var value = metricOf(county);
      var lift = coreCountyLiftPct(county);
      var bInfo = coreCountyBottleneck(county);
      var fill = coreMapMetric === "bottleneck"
        ? bInfo.color
        : colorFor(coreMapMetric === "lift" ? lift : value, maxMetric);
      var radius = 5 + 9 * Math.sqrt((county ? county.housing_units : 1) / result.housing_units);
      var selected = point.fips === selectedFips;
      var suffix = coreMapMetric === "bottleneck"
        ? ", " + bInfo.label + " (" + integer(value) + ")"
        : (coreMapMetric === "lift" ? ", " + (lift >= 0 ? "+" : "") + lift.toFixed(1) + "% lift (" + integer(value) + ")" : ", " + integer(value) + " calculated");
      var label = (county ? county.name : point.name) + suffix;
      return '<circle data-fips="' + point.fips + '" cx="' + xy[0].toFixed(1) +
        '" cy="' + xy[1].toFixed(1) + '" r="' + radius.toFixed(1) + '" fill="' + fill +
        '" stroke="' + (selected ? "#9a4e24" : "#1c2430") + '" stroke-width="' + (selected ? 2.5 : 0.6) +
        '"><title>' + escapeHtml(label) + "</title></circle>" +
        '<circle class="map-hit" data-fips="' + point.fips + '" cx="' + xy[0].toFixed(1) +
        '" cy="' + xy[1].toFixed(1) + '" r="12"><title>' + escapeHtml(label) + "</title></circle>";
    }).join("");
    mapStage.innerHTML =
      '<svg viewBox="0 0 ' + width + " " + height + '" role="group" aria-label="Map of ' + escapeHtml(result.name) + ' counties, colored by the selected scenario">' +
      '<rect width="100%" height="100%" fill="#f7f3ea"></rect>' +
      '<path d="' + hullPath + '" fill="#e7f0e4" stroke="#0f6b4e" stroke-width="1.5"></path>' +
      circles +
      "</svg>";
    bindMapKeys();
    bindRoving(mapStage, "[data-fips]");
    renderCountySelect();
    renderCountyDetail(selectedFips ? countyByFips(selectedFips) : null);
    renderCorePin();
  }

  function stateShape(code, pts, localBox, originX, originY, drawW, drawH) {
    var hull = convexHull(pts.map(function (point) { return project(point, localBox, drawW, drawH); }));
    if (hull.length < 3) return "";
    var path = hull.map(function (pair, index) {
      var x = pair[0] + originX;
      var y = pair[1] + originY;
      return (index === 0 ? "M" : "L") + x.toFixed(1) + " " + y.toFixed(1);
    }).join(" ") + " Z";
    var cx = 0;
    var cy = 0;
    hull.forEach(function (pair) { cx += pair[0] + originX; cy += pair[1] + originY; });
    cx /= hull.length;
    cy /= hull.length;
    var active = code === stateCode;
    return '<g role="button" tabindex="0" data-state="' + code + '">' +
      '<path d="' + path + '" fill="' + (active ? "#cfe6d8" : "#e4ecf5") + '" stroke="#1e3a5f" stroke-width="1.4"></path>' +
      '<text x="' + cx.toFixed(1) + '" y="' + (cy + 4).toFixed(1) + '" text-anchor="middle" font-size="13" font-family="sans-serif" fill="#1c2430">' + code + "</text>" +
      "<title>" + code + "</title></g>";
  }

  function renderNationMap() {
    mapTitle.textContent = "Eleven states";
    var groups = {};
    mapDoc.points.forEach(function (point) {
      if (!groups[point.state]) groups[point.state] = [];
      groups[point.state].push(point);
    });
    var insetCodes = { HI: true, CT: true, RI: true, NH: true };
    var mainland = mapDoc.points.filter(function (point) { return !insetCodes[point.state]; });
    var box = boundsOf(mainland);
    var width = 800;
    var height = 460;
    var shapes = Object.keys(groups).filter(function (code) { return !insetCodes[code]; }).map(function (code) {
      return stateShape(code, groups[code], box, 0, 0, width, height);
    }).join("");
    var hiBox = boundsOf(groups.HI || []);
    shapes += stateShape("HI", groups.HI || [], hiBox, 28, 330, 136, 100);
    [
      { code: "CT", x: 620, y: 40, w: 52, h: 136 },
      { code: "RI", x: 676, y: 40, w: 52, h: 136 },
      { code: "NH", x: 732, y: 40, w: 50, h: 136 },
    ].forEach(function (cell) {
      var pts = groups[cell.code] || [];
      if (!pts.length) return;
      shapes += stateShape(cell.code, pts, boundsOf(pts), cell.x, cell.y, cell.w, cell.h);
    });
    mapStage.innerHTML =
      '<svg viewBox="0 0 800 460" role="group" aria-label="Map of the eleven challenge states. Hawaii and southern New England are inset so the small states stay clickable.">' +
      '<rect width="100%" height="100%" fill="#f7f3ea"></rect>' +
      '<rect x="16" y="300" width="160" height="144" fill="#fffdf8" stroke="#d9d0c2"></rect>' +
      '<text x="24" y="316" font-size="12" font-family="sans-serif" fill="#5c6570">Hawaii</text>' +
      '<rect x="612" y="12" width="176" height="176" fill="#fffdf8" stroke="#d9d0c2"></rect>' +
      '<text x="620" y="28" font-size="11" font-family="sans-serif" fill="#5c6570">CT, RI, NH</text>' +
      shapes +
      "</svg>";
    bindMapKeys();
    bindRoving(mapStage, "[data-state]");
    countyDetail.hidden = true;
  }

  function bindRoving(container, selector) {
    var nodes = Array.prototype.slice.call(container.querySelectorAll(selector));
    var unique = [];
    var seen = {};
    nodes.forEach(function (node) {
      var key = node.getAttribute("data-fips") || node.getAttribute("data-state");
      if (seen[key]) return;
      seen[key] = true;
      unique.push(node);
    });
    unique.forEach(function (node, index) {
      node.tabIndex = index === 0 ? 0 : -1;
      node.addEventListener("keydown", function (event) {
        var next = index;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % unique.length;
        else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index - 1 + unique.length) % unique.length;
        else return;
        event.preventDefault();
        unique[index].tabIndex = -1;
        unique[next].tabIndex = 0;
        unique[next].focus();
      });
    });
  }

  function renderCountySelect() {
    var select = document.getElementById("county-select");
    if (!select || !result) return;
    select.innerHTML = result.counties.map(function (county) {
      return '<option value="' + county.fips + '"' + (county.fips === selectedFips ? " selected" : "") +
        ">" + escapeHtml(county.name) + "</option>";
    }).join("");
  }

  function bindMapKeys() {
    mapStage.querySelectorAll("[data-fips]").forEach(function (node) {
      function choose() {
        selectedFips = node.getAttribute("data-fips");
        renderStateMap();
      }
      node.addEventListener("click", choose);
      node.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          choose();
        }
      });
    });
    mapStage.querySelectorAll("[data-state]").forEach(function (node) {
      function choose() {
        mapScope = "state";
        selectedFips = null;
        selectState(node.getAttribute("data-state"));
      }
      node.addEventListener("click", choose);
      node.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          choose();
        }
      });
    });
  }

  function renderCase() {
    if (!caseStudy) {
      caseBody.innerHTML = "<p>Loading the Allegheny County walkthrough…</p>";
      return;
    }
    var steps = caseStudy.steps || [];
    var step = steps[caseStep] || steps[0];
    caseProgress.textContent = "Step " + (caseStep + 1) + " of " + steps.length + ". Allegheny County to Pennsylvania.";
    var related = (caseStudy.fields || []).filter(function (field) {
      if (step.id === "observed") return field.tag === "observed";
      if (step.id === "imputed") return field.tag === "assumed";
      if (step.id === "county" || step.id === "rollup") return field.tag === "calculated";
      return false;
    });
    var fieldHtml = related.map(function (field) {
      var formatter = Math.abs(field.value) >= 100 ? integer : oneDecimal;
      return '<article class="case-field"><strong>' + escapeHtml(field.label) + "</strong> " +
        tagged(field.value, field.tag, formatter) +
        "<p>" + escapeHtml(field.plain) + " Source: " + escapeHtml(field.source) + ".</p></article>";
    }).join("");
    caseBody.innerHTML =
      '<article class="case-step"><h3>' + escapeHtml(step.title) + "</h3><p class='plain'>" +
      escapeHtml(step.body) + "</p>" +
      (caseStudy.adu_fee_note && (step.id === "county" || step.id === "rollup")
        ? "<p class='adu-fee-note callout'>" + escapeHtml(caseStudy.adu_fee_note) + "</p>"
        : "") +
      "<div class='case-fields'>" + fieldHtml + "</div></article>";
  }

  function fillAduFeeNote() {
    var el = document.getElementById("adu-fee-note");
    if (el && aduCompare) el.innerHTML = aduCompare.notes.core_html;
    var gap = document.getElementById("engine-gap");
    if (!gap) return;
    if (stateCode === "PA" || stateCode === "NH") {
      if (aduCompare && aduCompare.notes.engine_gap_core_html) {
        gap.innerHTML = aduCompare.notes.engine_gap_core_html;
      }
    } else if (result) {
      gap.innerHTML =
        "<p class='gap-prose'><strong>Model scope (" + escapeHtml(result.name) + " · Tier " + escapeHtml(result.tier) + "):</strong> " +
        "These figures come from the eleven-state structural screening engine (<code>src/model/equations.py</code>). " +
        "The lot-competition Small Homes Policy Lab covers Pennsylvania and New Hampshire; " +
        '<a href="/lab" style="display:inline-block;min-height:24px">open the Lab</a> or ' +
        '<a href="#adu-fee-note" style="display:inline-block;min-height:24px">see the PA/NH 5-step model bridge</a>.</p>';
    }
  }

  function loadCaseStudy() {
    setStatus("Opening the Pennsylvania case study…");
    return post("/api/case-study", { overrides: overrides, reforms: reformsPayload() })
      .then(function (payload) {
        caseStudy = payload;
        renderCase();
        setStatus("");
      })
      .catch(fail);
  }

  function render() {
    if (result.provenance_legend) {
      LEGEND.observed = result.provenance_legend.observed || LEGEND.observed;
      LEGEND.assumed = result.provenance_legend.assumed || LEGEND.assumed;
      LEGEND.calculated = result.provenance_legend.calculated || LEGEND.calculated;
    }
    fillAduFeeNote();
    renderHeadline();
    renderCards();
    renderCompare();
    renderMath();
    renderCounties();
    renderLimits();
    renderBrief();
    renderMap();
    renderCorePresets();
    renderCorePin();
    if (!document.getElementById("panel-case").hidden) renderCase();
  }

  function renderTornado(payload) {
    var rows = (payload.parameters || []).slice(0, 12);
    if (!rows.length) {
      tornado.textContent = "No slider moved this outcome.";
      return;
    }
    var min = Infinity;
    var max = -Infinity;
    rows.forEach(function (row) {
      min = Math.min(min, row.low, row.high, row.central);
      max = Math.max(max, row.low, row.high, row.central);
    });
    var span = max - min || 1;
    function pos(value) { return ((value - min) / span) * 100; }
    tornado.innerHTML = "<p class='help'>Bar endpoints are calculated outcomes. The low and high inputs that produce them are assumed.</p>";
    rows.forEach(function (row) {
      var line = document.createElement("div");
      line.className = "tornado-row";
      var lowLeft = Math.min(pos(row.low), pos(row.central));
      var highLeft = Math.min(pos(row.high), pos(row.central));
      line.innerHTML =
        "<span>" + escapeHtml(row.label) + "</span>" +
        '<div class="tornado-track" title="Low ' + integer(row.low) + " calculated · central " + integer(row.central) + " calculated · high " + integer(row.high) + ' calculated">' +
        '<i class="axis" style="left:' + pos(row.central) + '%"></i>' +
        '<i class="low" style="left:' + lowLeft + "%;width:" + Math.abs(pos(row.low) - pos(row.central)) + '%"></i>' +
        '<i class="high" style="left:' + highLeft + "%;width:" + Math.abs(pos(row.high) - pos(row.central)) + '%"></i>' +
        "</div>";
      tornado.appendChild(line);
    });
  }

  function renderBand(mc) {
    lastBand = mc;
    var central = scenarioId === "baseline" ? result.baseline_completions_5yr : result.scenarios[scenarioId].incremental_completions;
    var flag = mc.crosses_zero ? ' <span class="badge-uncertain" title="The published assumption range includes both a gain and a loss.">Outcome uncertain: under some assumptions this reform adds no homes.</span>' : "";
    band.className = "callout" + (mc.crosses_zero ? " warn" : "");
    band.innerHTML = "<strong>Seeded band, " + tagged(mc.draws, tagOf(mc, "draws", "assumed"), integer) +
      " draws, seed " + tagged(mc.seed, tagOf(mc, "seed", "assumed"), integer) + ".</strong> " +
      "p10 " + tagged(mc.p10, "calculated", integer) +
      " · p50 " + tagged(mc.p50, "calculated", integer) +
      " · p90 " + tagged(mc.p90, "calculated", integer) +
      ". The central point, with sliders at their current values, is " + tagged(central, "calculated", integer) +
      ". Each draw samples every slider from a triangle on its published low-to-high band. " +
      "An override becomes that slider's mode and the draw still varies." + flag;
    renderCards();
    renderCompare();
    renderBrief();
  }

  function renderCross(payload) {
    var names = {
      adu: "ADUs",
      missing_middle: "Missing middle",
      tod: "TOD",
      parking: "Parking",
      fees: "Fees",
      combined: "Package",
    };
    crossOut.innerHTML = "";
    var roiBanner = document.createElement("div");
    roiBanner.className = "callout";
    roiBanner.innerHTML =
      "<strong>50-state portability &amp; data-investment ROI.</strong> " +
      "Every U.S. state can run immediately in Tier-2 mode using free public Census ACS, Building Permits Survey, and TIGER gazetteer files (<code>scripts/get_data.sh</code>) with zero proprietary vendor licenses. " +
      "Masking statewide parcel extracts on the four Tier-1 states below measures the exact empirical error of running without parcel data versus collapsing county price variation to a single state median.";
    crossOut.appendChild(roiBanner);
    if (payload.note) {
      var intro = document.createElement("p");
      intro.className = "help";
      intro.textContent = payload.note;
      crossOut.appendChild(intro);
    }
    Object.keys(payload.states || {}).forEach(function (code) {
      var item = payload.states[code];
      var cardEl = document.createElement("article");
      cardEl.className = "cross-card";
      var ratio = item.band_width_ratio == null ? "—" : Number(item.band_width_ratio).toFixed(2) + "×";
      var html = "<h3>" + code + " · tier " + item.tier + " " + badge(tagOf(item, "tier", "observed")) + "</h3>" +
        "<p>Lot feasibility " + tagged(item.lot_full, tagOf(item, "lot_full"), function (value) { return Math.round(value * 100) + "%"; }) +
        " with the extract, " +
        tagged(item.lot_imputed, tagOf(item, "lot_imputed", "assumed"), function (value) { return Math.round(value * 100) + "%"; }) +
        " when the extract is hidden. Package band width " +
        tagged(item.band_width_full, "calculated", integer) + " full versus " +
        tagged(item.band_width_imputed, "calculated", integer) + " imputed (" + escapeHtml(ratio) + ").</p>" +
        "<table><thead><tr><th>Scenario</th><th>Full</th><th>Hidden parcels</th><th>Error</th><th>State median screen</th><th>Error</th></tr></thead><tbody>";
      Object.keys(names).forEach(function (id) {
        var block = item.scenarios[id];
        html += "<tr><td>" + names[id] + "</td><td>" + tagged(block.imputed_parcels.full, "calculated", integer) +
          "</td><td>" + tagged(block.imputed_parcels.other, "calculated", integer) +
          "</td><td>" + errorText(block.imputed_parcels) +
          "</td><td>" + tagged(block.state_screen.other, "calculated", integer) +
          "</td><td>" + errorText(block.state_screen) + "</td></tr>";
      });
      html += "</tbody></table>";
      cardEl.innerHTML = html;
      crossOut.appendChild(cardEl);
    });
  }

  function errorText(block) {
    if (block.percent_error == null) return '<span class="badge-error">' + integer(block.gap) + " (small base)</span>";
    return '<span class="badge-error">' + signedPercent(block.percent_error) + "</span> " + badge("calculated");
  }

  function selectScenario(id) {
    scenarioId = id;
    lastBand = null;
    if (result) {
      renderCards();
      renderCompare();
      renderMath();
      renderLimits();
      renderBrief();
      renderMap();
    }
    tornado.innerHTML = "";
    band.textContent = "Run the tornado to see which published assumptions move " + id.replace(/_/g, " ") + ".";
  }

  function markActiveState() {
    document.querySelectorAll("#state-list .state-btn").forEach(function (button) {
      var name = button.querySelector("strong").textContent;
      var active = result && name === result.name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  async function ensureAduCompare(code) {
    var target = (code === "NH") ? "NH" : "PA";
    if (aduCompareCache[target]) {
      aduCompare = aduCompareCache[target];
      return;
    }
    var doc = await request("/api/adu-compare?state=" + encodeURIComponent(target));
    aduCompareCache[target] = doc;
    aduCompare = doc;
  }

  async function selectState(code) {
    stateCode = code;
    overrides = {};
    corePinned = null;
    tornado.innerHTML = "";
    band.textContent = "";
    lastBand = null;
    heroBand = null;
    setStatus("Loading " + code + "…");
    var specPromise = request("/api/assumptions?state=" + encodeURIComponent(code));
    var bridgePromise = ensureAduCompare(code);
    var spec = await specPromise;
    await bridgePromise;
    parameters = spec.parameters;
    renderSliders();
    await simulate();
    markActiveState();
  }

  function loadHeroBand() {
    var bid = ++bandRequestId;
    heroBandLoading = true;
    renderHeadline();
    post("/api/sensitivity", {
      state: stateCode,
      scenario: "combined",
      draws: 80,
      overrides: overrides,
      reforms: reformsPayload(),
    })
      .then(function (payload) {
        if (bid !== bandRequestId) return;
        heroBand = payload && payload.monte_carlo ? payload.monte_carlo : null;
        heroBandLoading = false;
        if (result) renderHeadline();
      })
      .catch(function () {
        if (bid !== bandRequestId) return;
        heroBand = null;
        heroBandLoading = false;
        if (result) renderHeadline();
      });
  }

  async function simulate() {
    var id = ++requestId;
    setStatus("Calculating " + stateCode + "…");
    var next = await post("/api/simulate", {
      state: stateCode,
      overrides: overrides,
      reforms: reformsPayload(),
    });
    if (id !== requestId) return;
    result = next;
    heroBand = null;
    setStatus("");
    render();
    loadHeroBand();
    if (caseStudy && stateCode === "PA") {
      caseStudy = null;
    }
  }

  function fail(error) {
    setStatus(error && error.message ? error.message : "Something went wrong.");
  }

  function runCrossCheck() {
    setStatus("Cross-checking CT, WI, UT, and HI. This samples the published bands.");
    return post("/api/crossval", { scope: "tier1", draws: 40 })
      .then(function (payload) {
        renderCross(payload);
        setStatus("");
      })
      .catch(fail);
  }

  function activateTab(tab) {
    document.querySelectorAll(".tab").forEach(function (other) {
      var on = other === tab;
      other.classList.toggle("active", on);
      other.setAttribute("aria-selected", on ? "true" : "false");
      other.tabIndex = on ? 0 : -1;
    });
    document.querySelectorAll(".panel").forEach(function (panel) {
      var on = panel.id === "panel-" + tab.getAttribute("data-tab");
      panel.hidden = !on;
      panel.classList.toggle("active", on);
    });
    if (tab.getAttribute("data-tab") === "case" && !caseStudy) {
      loadCaseStudy();
    }
    if (tab.getAttribute("data-tab") === "cross" && !crossOut.innerHTML.trim()) {
      runCrossCheck();
    }
    if (tab.getAttribute("data-tab") === "brief" && result) renderBrief();
  }

  var tabButtons = Array.prototype.slice.call(document.querySelectorAll(".tab"));
  tabButtons.forEach(function (tab, index) {
    tab.tabIndex = tab.classList.contains("active") ? 0 : -1;
    tab.addEventListener("click", function () { activateTab(tab); });
    tab.addEventListener("keydown", function (event) {
      var next = index;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % tabButtons.length;
      else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index - 1 + tabButtons.length) % tabButtons.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabButtons.length - 1;
      else return;
      event.preventDefault();
      activateTab(tabButtons[next]);
      tabButtons[next].focus();
    });
  });

  var moreBtn = document.getElementById("more-tabs");
  var moreList = document.getElementById("more-tab-list");
  if (moreBtn && moreList) {
    moreBtn.addEventListener("click", function () {
      var open = moreList.hidden;
      moreList.hidden = !open;
      moreBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  var openPortability = document.getElementById("open-portability");
  if (openPortability) {
    openPortability.addEventListener("click", function () {
      if (moreList && moreList.hidden) {
        moreList.hidden = false;
        if (moreBtn) moreBtn.setAttribute("aria-expanded", "true");
      }
      var crossTab = document.getElementById("tab-cross");
      var crossPanel = document.getElementById("panel-cross");
      if (crossTab) activateTab(crossTab);
      if (crossPanel && crossPanel.scrollIntoView) {
        crossPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  var countyPick = document.getElementById("county-select");
  if (countyPick) {
    countyPick.addEventListener("change", function () {
      selectedFips = countyPick.value;
      mapScope = "state";
      renderMap();
    });
  }

  document.getElementById("reset").addEventListener("click", function () {
    overrides = {};
    REFORMS.forEach(function (id) {
      reformOn[id] = true;
      reformWeight[id] = 1;
    });
    renderReformMix();
    renderSliders();
    simulate().catch(fail);
  });

  document.getElementById("map-back").addEventListener("click", function () {
    mapScope = "nation";
    selectedFips = null;
    renderMap();
  });

  document.getElementById("export-csv").addEventListener("click", function () { download("csv"); });
  document.getElementById("export-json").addEventListener("click", function () { download("json"); });
  document.getElementById("export-md").addEventListener("click", function () { download("md"); });
  document.getElementById("print-brief").addEventListener("click", function () { window.print(); });

  document.getElementById("case-prev").addEventListener("click", function () {
    if (!caseStudy) return;
    caseStep = Math.max(0, caseStep - 1);
    renderCase();
  });
  document.getElementById("case-next").addEventListener("click", function () {
    if (!caseStudy) return;
    caseStep = Math.min(caseStudy.steps.length - 1, caseStep + 1);
    if (caseStep >= 1 && stateCode !== "PA") {
      mapScope = "state";
      selectedFips = "42003";
      selectState("PA").then(function () { renderCase(); }).catch(fail);
      return;
    }
    if (caseStep >= 3) {
      selectedFips = "42003";
      mapScope = "state";
      if (result) renderMap();
    }
    renderCase();
  });

  document.getElementById("run-sensitivity").addEventListener("click", function () {
    setStatus("Running the tornado and the seeded band…");
    post("/api/sensitivity", {
      state: stateCode,
      scenario: scenarioId,
      draws: 80,
      overrides: overrides,
      reforms: reformsPayload()
    })
      .then(function (payload) {
        var scope = document.getElementById("sensitivity-scope");
        if (scope) scope.textContent = payload.scenario_label || "";
        renderTornado(payload.tornado);
        renderBand(payload.monte_carlo);
        setStatus("");
      })
      .catch(fail);
  });

  document.getElementById("run-cross").addEventListener("click", function () {
    runCrossCheck();
  });

  async function download(fmt) {
    setStatus("Preparing the " + fmt.toUpperCase() + " export…");
    var response = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        state: stateCode,
        format: fmt,
        overrides: overrides,
        reforms: reformsPayload()
      })
    });
    if (!response.ok) {
      setStatus("Export failed.");
      return;
    }
    var blob = await response.blob();
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    var extension = fmt === "md" ? "md" : fmt;
    link.href = url;
    link.download = "stateframe-" + stateCode + "." + extension;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setStatus("");
  }

  renderReformMix();
  renderCorePresets();
  Promise.all([request("/api/states"), request("/api/map"), request("/api/adu-compare?state=PA")])
    .then(function (payloads) {
      mapDoc = payloads[1];
      aduCompareCache.PA = payloads[2];
      aduCompare = payloads[2];
      fillAduFeeNote();
      renderStates(payloads[0].states);
      var known = (payloads[0].states || []).some(function (row) { return row.code === stateCode; });
      return selectState(known ? stateCode : "PA");
    })
    .catch(fail);
})();
