/* Stateframe v3 Legislative Studio client (11-State Screening Lens).
   Recalculates live by calling the structural equation server (src/model/equations.py).
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
  var scenarioId = "combined";
  var studioDepth = "briefing";
  var parameters = [];
  var overrides = {};
  var reformOn = { adu: true, missing_middle: true, tod: true, parking: true, fees: true };
  (function readEntry() {
    var q = new URLSearchParams(location.search);
    var st = (q.get("st") || "").toUpperCase();
    if (st) stateCode = st;
    var depthParam = (q.get("depth") || "").toLowerCase();
    if (depthParam === "briefing" || depthParam === "markup" || depthParam === "audit") {
      studioDepth = depthParam;
    }
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
  var stateCatalog = [];
  var result = null;
  var mapDoc = null;
  var geoAllDoc = null;
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
  var dataSourcesDoc = null;
  var insightsDoc = null;
  var singleStairOn = false;
  var activeStanceId = "balanced";
  var insightsRequestId = 0;

  var statusEl = document.getElementById("status");
  var stateList = document.getElementById("state-list");
  var studioStateSelect = document.getElementById("studio-state-select");
  var statesDrawer = document.getElementById("states-drawer");
  var assumptionsDrawer = document.getElementById("assumptions-drawer");
  var studioBackdrop = document.getElementById("studio-backdrop");
  var overrideBadge = document.getElementById("override-badge");
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
  var insightsMount = document.getElementById("insights-mount");
  var briefingStripMount = document.getElementById("briefing-strip-mount");

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || "";
  }

  function setStudioDepth(nextDepth, skipTabSwitch) {
    if (nextDepth !== "briefing" && nextDepth !== "markup" && nextDepth !== "audit") {
      nextDepth = "briefing";
    }
    studioDepth = nextDepth;
    if (document.body) {
      document.body.setAttribute("data-depth", studioDepth);
    }
    document.querySelectorAll("[data-depth-btn]").forEach(function (btn) {
      var on = btn.getAttribute("data-depth-btn") === studioDepth;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (!skipTabSwitch && studioDepth === "markup") {
      var insTab = document.getElementById("tab-insights");
      if (insTab) activateTab(insTab, true);
    }
  }

  function closeDrawers() {
    if (statesDrawer) statesDrawer.hidden = true;
    if (assumptionsDrawer) assumptionsDrawer.hidden = true;
    if (studioBackdrop) studioBackdrop.hidden = true;
    var btnStates = document.getElementById("toggle-states-drawer");
    var btnAssump = document.getElementById("toggle-assumptions-drawer");
    if (btnStates) btnStates.setAttribute("aria-expanded", "false");
    if (btnAssump) btnAssump.setAttribute("aria-expanded", "false");
  }

  function openDrawer(which) {
    closeDrawers();
    if (which === "states" && statesDrawer) {
      statesDrawer.hidden = false;
      if (studioBackdrop) studioBackdrop.hidden = false;
      var btnStates = document.getElementById("toggle-states-drawer");
      if (btnStates) btnStates.setAttribute("aria-expanded", "true");
      var closeBtn = document.getElementById("close-states-drawer");
      if (closeBtn) closeBtn.focus();
    } else if (which === "assumptions" && assumptionsDrawer) {
      assumptionsDrawer.hidden = false;
      if (studioBackdrop) studioBackdrop.hidden = false;
      var btnAssump = document.getElementById("toggle-assumptions-drawer");
      if (btnAssump) btnAssump.setAttribute("aria-expanded", "true");
      var closeAssump = document.getElementById("close-assumptions-drawer");
      if (closeAssump) closeAssump.focus();
    }
  }

  function updateOverrideBadge() {
    if (!overrideBadge) return;
    var count = Object.keys(overrides).length;
    REFORMS.forEach(function (id) {
      if (!reformOn[id] || Math.abs(Number(reformWeight[id]) - 1) > 1e-6) count += 1;
    });
    if (singleStairOn) count += 1;
    overrideBadge.hidden = count === 0;
    overrideBadge.textContent = String(count);
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
    stateCatalog = catalog || [];
    stateList.innerHTML = "";
    if (studioStateSelect) {
      var allOpt = '<option value="ALL"' + (mapScope === "nation" ? " selected" : "") + ">All 11 states (476 counties)</option>";
      studioStateSelect.innerHTML = allOpt + stateCatalog.map(function (st) {
        return '<option value="' + escapeHtml(st.code) + '"' + (mapScope !== "nation" && st.code === stateCode ? " selected" : "") + ">" +
          escapeHtml(st.code + " · " + st.name + " (Tier " + st.tier + ")") + "</option>";
      }).join("");
    }
    stateCatalog.forEach(function (state) {
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
        closeDrawers();
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
    updateOverrideBadge();
    renderReformMix();
    renderSliders();
    schedule();
  }

  function populatePresetsContainer(box) {
    if (!box) return;
    box.innerHTML =
      '<p class="aside-label">Committee amendment presets</p>' +
      '<p class="hint">Load a common legislative bill configuration inside published assumption bands.</p>' +
      '<div class="preset-grid">' +
      CORE_PRESETS.map(function (p) {
        return '<button type="button" class="preset-btn" data-core-preset="' + escapeHtml(p.id) +
          '" aria-label="' + escapeHtml(p.label + " — " + p.desc) + '">' + escapeHtml(p.label) + "</button>";
      }).join("") +
      "</div>";
    box.querySelectorAll("[data-core-preset]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        applyCorePreset(btn.getAttribute("data-core-preset"));
      });
    });
  }

  function renderCorePresets() {
    populatePresetsContainer(document.getElementById("core-presets"));
    populatePresetsContainer(document.getElementById("core-presets-inline"));
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

  function populatePinContainer(box, suffix) {
    if (!box || !result) return;
    if (!corePinned || corePinned.state !== stateCode) {
      box.innerHTML =
        '<div class="pin-head"><span class="aside-label">Compare bills (A vs. B)</span>' +
        '<button type="button" class="pin-act" id="core-pin-save' + suffix + '">Pin current as A</button></div>' +
        '<p class="hint">Pin this package, then adjust weights or sliders to compare Bill B against Bill A.</p>';
      var saveBtn = box.querySelector("#core-pin-save" + suffix);
      if (saveBtn) saveBtn.addEventListener("click", pinCoreCurrent);
      return;
    }
    var curPkg = Number(result.scenarios.combined.incremental_completions) || 0;
    var dPkg = curPkg - corePinned.packageNet;
    var cObj = selectedFips ? countyByFips(selectedFips) : null;
    var curC = cObj ? (Number(cObj.combined) || 0) : 0;
    var pinC = (cObj && Object.prototype.hasOwnProperty.call(corePinned.byCounty, cObj.fips)) ? corePinned.byCounty[cObj.fips] : 0;
    var dC = curC - pinC;
    var cShort = cObj ? String(cObj.name || "").replace(/ County$/i, "") : "";
    var diffStr = (dPkg > 0 ? "+" : "") + integer(dPkg);
    var cDiffStr = (dC > 0 ? "+" : "") + integer(dC);
    box.innerHTML =
      '<div class="pin-head"><span class="aside-label">Pinned A vs. Current B</span>' +
      '<span class="pin-btns"><button type="button" class="pin-act" id="core-pin-update' + suffix + '">Re-pin</button>' +
      '<button type="button" class="pin-act" id="core-pin-clear' + suffix + '">Clear</button></span></div>' +
      '<p class="hint">Pinned A: <strong>' + escapeHtml(corePinned.label) + "</strong></p>" +
      '<div class="pin-table-wrap"><table class="pin-table" aria-label="Pinned package A versus current package B">' +
      "<thead><tr><th>Scope</th><th>Bill A</th><th>Bill B</th><th>Δ (B−A)</th></tr></thead><tbody>" +
      "<tr><td>" + escapeHtml(stateCode) + " net</td><td>" + integer(corePinned.packageNet) + "</td><td>" +
      integer(curPkg) + "</td><td><strong>" + diffStr + "</strong></td></tr>" +
      (cObj
        ? "<tr><td>" + escapeHtml(cShort) + "</td><td>" + integer(pinC) + "</td><td>" +
          integer(curC) + "</td><td><strong>" + cDiffStr + "</strong></td></tr>"
        : "") +
      "</tbody></table></div>";
    var upBtn = box.querySelector("#core-pin-update" + suffix);
    var clBtn = box.querySelector("#core-pin-clear" + suffix);
    if (upBtn) upBtn.addEventListener("click", pinCoreCurrent);
    if (clBtn) clBtn.addEventListener("click", function () { corePinned = null; renderCorePin(); });
  }

  function renderCorePin() {
    populatePinContainer(document.getElementById("core-pin"), "");
    populatePinContainer(document.getElementById("core-pin-inline"), "-inline");
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
        updateOverrideBadge();
        schedule();
      });
      range.addEventListener("input", function () {
        reformWeight[id] = Number(range.value);
        value.textContent = Math.round(reformWeight[id] * 100) + "%";
        updateOverrideBadge();
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
          updateOverrideBadge();
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
    var rangeLine = hasRange
      ? '<p class="range-hero">Likely ' + integer(heroBand.p10) + joiner + integer(heroBand.p90) +
        ' extra homes <span class="range-kicker">(10th–90th percentile · ' + integer(heroBand.draws) + " draws)</span></p>"
      : '<p class="range-hero is-loading">' +
        (heroBandLoading ? "Sampling 80-draw assumption band…" : "Likely range unavailable") + "</p>";
    var funnelNote = window.StateframeFrame ? window.StateframeFrame.FUNNEL_UNAVAILABLE : "";
    headline.innerHTML =
      '<div class="hero-summary">' +
      '<div class="hero-summary-top">' +
      '<span class="step-kicker">Live Statewide 5-Year Verdict</span>' +
      '<span class="model-badge screening">Screening Lens · Tier ' + escapeHtml(result.tier) + " · " + escapeHtml(result.code || stateCode) + "</span>" +
      "</div>" +
      '<p class="headline-answer">' + escapeHtml(answer) + badge("calculated") + "</p>" +
      rangeLine +
      '<p class="middle-est">Middle estimate <span data-bind="scenarios.combined.incremental_completions">' +
      integer(pack) + '</span> extra homes (' + escapeHtml(signedPercent(lift)) + '), on top of <span data-bind="baseline_completions_5yr">' +
      integer(result.baseline_completions_5yr) + "</span> expected." +
      (funnelNote ? ' <span class="funnel-note">· ' + escapeHtml(funnelNote) + "</span>" : "") + "</p>" +
      "</div>" +
      card(
        "Baseline completions",
        tagged(result.baseline_completions_5yr, tagOf(result, "baseline_completions_5yr"), integer),
        "Five-year homes completed if current permit pace continues."
      ) +
      card(
        "Package, net new",
        tagged(pack, "calculated", integer),
        signedPercent(lift) + " vs. baseline · Overlap removed."
      ) +
      card(
        "Walkshed",
        tagged(result.walkshed_sqmi, tagOf(result, "walkshed_sqmi"), function (value) { return oneDecimal(value) + " sq mi"; }),
        "Transit station area after overlap discount."
      ) +
      card(
        "Lot screen",
        tagged(result.lot_feasible_share, lotTag, function (value) { return Math.round(value * 100) + "%"; }),
        result.lot_feasible_note || "Feasible single-family lot share."
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
    /* Show combined package first, then the 5 standalone reforms ranked/ordered, plus baseline */
    var studioOrder = ["combined", "adu", "missing_middle", "tod", "parking", "fees", "baseline"];
    studioOrder.forEach(function (id) {
      var row = result.scenarios[id];
      var article = document.createElement("article");
      var off = id !== "baseline" && id !== "combined" && !reformOn[id];
      article.className = "scenario-card" + (id === scenarioId ? " selected" : "") + (off ? " off" : "") +
        (id === "combined" ? " is-package-card" : "");
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
          updateOverrideBadge();
          renderReformMix();
          schedule();
        });
        label.appendChild(box);
        label.appendChild(document.createTextNode("In package"));
        top.appendChild(label);
      } else if (id === "combined") {
        var activeCount = REFORMS.filter(function (rid) { return !!reformOn[rid]; }).length;
        var pkgPill = document.createElement("span");
        pkgPill.className = "pill t1";
        pkgPill.textContent = activeCount + " of 5 bills on";
        top.appendChild(pkgPill);
      }
      article.appendChild(top);
      if (close) {
        var flag = document.createElement("p");
        flag.className = "card-close-flag";
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
        "<div><div class='k'>Net new</div><div class='v net-highlight'>" + tagged(net, "calculated", integer) + "</div></div>";
      article.appendChild(grid);
      titleBtn.setAttribute("aria-pressed", id === scenarioId ? "true" : "false");
      function choose() { selectScenario(id); }
      titleBtn.addEventListener("click", function (event) {
        event.stopPropagation();
        choose();
      });
      article.addEventListener("click", function (event) {
        if (event.target && (event.target.tagName === "INPUT" || event.target.tagName === "LABEL")) return;
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
      if (county.fips === selectedFips) tr.className = "selected";
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
        if (studioStateSelect) studioStateSelect.value = stateCode;
        renderMap();
        loadInsights();
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
      "<p>Housing stock and prices are Census ACS figures. Permits are the Building Permits Survey. County boundaries are Census cb_2024_us_county_5m cartographic polygons. County integers sum to the rounded state total. Open-source under Apache-2.0.</p>" +
      "</div>";
  }

  function pointsFor(code) {
    if (!mapDoc || !mapDoc.points) return [];
    return mapDoc.points.filter(function (point) { return point.state === code; });
  }

  function geoCountiesFor(code) {
    if (!geoAllDoc || !geoAllDoc.states) return [];
    return geoAllDoc.states[code] || [];
  }

  function boundsOfRings(counties) {
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

  function defaultFocusFips() {
    if (!result || !result.counties || !result.counties.length) return null;
    if (result.focus_county) {
      var target = String(result.focus_county).toLowerCase();
      for (var i = 0; i < result.counties.length; i += 1) {
        if (String(result.counties[i].name || "").toLowerCase().indexOf(target) >= 0) {
          return result.counties[i].fips;
        }
      }
    }
    var best = result.counties[0];
    result.counties.forEach(function (c) {
      if ((Number(c.housing_units) || 0) > (Number(best.housing_units) || 0)) best = c;
    });
    return best ? best.fips : null;
  }

  function metricOf(county) {
    if (!county) return 0;
    return Number(county[scenarioColumn(scenarioId)] || 0);
  }

  function choroplethColor(value, max) {
    if (!max || value <= 0) return "#dce6f0";
    var t = Math.sqrt(Math.max(0, Math.min(1, value / max)));
    var h = Math.round(205 - 38 * t);
    var s = Math.round(35 + 36 * t);
    var l = Math.round(86 - 52 * t);
    return "hsl(" + h + "," + s + "%," + l + "%)";
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
    var toolbar = box && box.closest ? box.closest(".map-toolbar") : null;
    var leg = document.getElementById("core-bottleneck-legend");
    if (!box) return;
    if (mapScope === "nation") {
      box.hidden = true;
      if (toolbar) toolbar.hidden = true;
      if (leg) leg.hidden = true;
      return;
    }
    box.hidden = false;
    if (toolbar) toolbar.hidden = false;
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
    var chosenScenario = result.scenarios[scenarioId] || result.scenarios.combined;
    var bInfo = coreCountyBottleneck(county);
    var lift = coreCountyLiftPct(county);
    var liftText = scenarioId === "baseline" ? "baseline view" : ((lift >= 0 ? "+" : "") + lift.toFixed(1) + "% vs. baseline");
    countyDetail.hidden = false;
    countyDetail.innerHTML =
      '<div class="receipt-card-head">' +
        '<div><span class="step-kicker">Pinned County Receipt · ' + escapeHtml(county.context || "County") + '</span>' +
        "<strong>" + escapeHtml(county.name) + "</strong> " +
        '<span class="b-pill ' + escapeHtml(bInfo.id) + '">' + escapeHtml(bInfo.label) + "</span> " +
        (county.close_call ? '<span class="badge-uncertain" title="The published assumption range includes both a gain and a loss.">Outcome uncertain</span>' : "") +
        "</div>" +
        '<div class="receipt-hero-kpi"><span class="k">' + escapeHtml(chosenScenario.label) + '</span>' +
        '<span class="v">' + (scenarioId === "baseline" ? "" : "+") + tagged(county[column], "calculated", integer) + "</span>" +
        '<span class="s">' + escapeHtml(liftText) + "</span></div>" +
      "</div>" +
      '<div class="receipt-mini-grid">' +
        "<div><span>Existing homes</span><strong>" + tagged(county.housing_units, "observed", integer) + "</strong></div>" +
        "<div><span>Median value</span><strong>" + tagged(county.median_value, valueTag, function (v) { return "$" + integer(v); }) + "</strong></div>" +
        "<div><span>5-yr baseline</span><strong>" + tagged(county.baseline_completions, "calculated", integer) + "</strong></div>" +
        "<div><span>Full 5-bill pkg</span><strong>+" + tagged(county.combined, "calculated", integer) + "</strong></div>" +
      "</div>" +
      "<p class='plain'>" + escapeHtml(bInfo.note) + " " +
      escapeHtml(county.close_call_reason || "County integers sum to the statewide total.") + "</p>" +
      '<div class="exports">' +
        '<button type="button" class="btn-pill" id="county-open-insights">Inspect ' + escapeHtml(county.name) + " HUD AMI breakeven &amp; GIS</button>" +
        '<button type="button" class="btn-pill" id="county-open-math">Trace county-to-state equations</button>' +
      "</div>";
    var jumpBtn = document.getElementById("county-open-insights");
    if (jumpBtn) {
      jumpBtn.addEventListener("click", function () {
        setStudioDepth("markup", true);
        var tab = document.getElementById("tab-insights");
        var panel = document.getElementById("panel-insights");
        if (tab) activateTab(tab, true);
        if (panel && panel.scrollIntoView) panel.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
    var mathBtn = document.getElementById("county-open-math");
    if (mathBtn) {
      mathBtn.addEventListener("click", function () {
        setStudioDepth("audit", true);
        var tab = document.getElementById("tab-math");
        var panel = document.getElementById("panel-math");
        if (tab) activateTab(tab, true);
        if (panel && panel.scrollIntoView) panel.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }

  function renderMap() {
    renderCoreMapMetrics();
    if (!result || (!mapDoc && !geoAllDoc)) {
      mapStage.textContent = "County cartographic boundaries are loading…";
      return;
    }
    if (mapScope === "nation") renderNationMap();
    else renderStateMap();
  }

  function renderStateMap() {
    var chosenScenario = result.scenarios[scenarioId] || result.scenarios.combined;
    mapTitle.textContent = result.name + " · " + chosenScenario.label;
    if (!selectedFips || !countyByFips(selectedFips)) {
      selectedFips = defaultFocusFips();
    }
    var geoCounties = geoCountiesFor(stateCode);
    var width = 800;
    var height = 500;
    var maxMetric = 0;
    var bCounts = { zoning: 0, fee: 0, market: 0 };
    (result.counties || []).forEach(function (c) {
      var m = coreMapMetric === "lift" ? coreCountyLiftPct(c) : metricOf(c);
      maxMetric = Math.max(maxMetric, Math.abs(m));
      var b = coreCountyBottleneck(c);
      bCounts[b.id] = (bCounts[b.id] || 0) + 1;
    });

    var bLeg = document.getElementById("core-bottleneck-legend");
    if (bLeg) {
      bLeg.hidden = false;
      if (coreMapMetric === "bottleneck") {
        bLeg.innerHTML =
          '<span class="b-dot zoning"></span> Zoning-locked (' + bCounts.zoning + ") · " +
          '<span class="b-dot fee"></span> Fee-sensitive (' + bCounts.fee + ") · " +
          '<span class="b-dot market"></span> Rent/cost-constrained (' + bCounts.market + ")";
      } else if (coreMapMetric === "lift") {
        bLeg.innerHTML = '<span class="choropleth-ramp" aria-hidden="true"></span> Polygon shade shows 5-year % lift over baseline completions (peak ' +
          signedPercent(maxMetric) + ").";
      } else {
        bLeg.innerHTML = '<span class="choropleth-ramp" aria-hidden="true"></span> Polygon shade shows 5-year net homes for <strong>' +
          escapeHtml(chosenScenario.label) + "</strong> (peak +" + integer(maxMetric) + " in one county).";
      }
    }

    if (geoCounties.length) {
      var box = boundsOfRings(geoCounties);
      var midLat = ((box.minY + box.maxY) / 2) * Math.PI / 180;
      var xspan = Math.max(0.05, (box.maxX - box.minX) * Math.cos(midLat));
      var yspan = Math.max(0.05, box.maxY - box.minY);
      var pad = 20;
      var scale = Math.min((width - 2 * pad) / xspan, (height - 2 * pad) / yspan);
      var drawW = xspan * scale;
      var drawH = yspan * scale;
      var offX = (width - drawW) / 2;
      var offY = (height - drawH) / 2;
      var xy = function (lon, lat) {
        return [
          offX + (lon - box.minX) * Math.cos(midLat) * scale,
          height - offY - (lat - box.minY) * scale,
        ];
      };

      var selectedPathHtml = "";
      var paths = geoCounties.map(function (gc) {
        var county = countyByFips(gc.fips);
        var value = metricOf(county);
        var lift = coreCountyLiftPct(county);
        var bInfo = coreCountyBottleneck(county);
        var fill = coreMapMetric === "bottleneck"
          ? bInfo.color
          : choroplethColor(coreMapMetric === "lift" ? lift : value, maxMetric);
        var d = (gc.rings || []).map(function (ring) {
          return ring.map(function (pt, idx) {
            var p = xy(pt[0], pt[1]);
            return (idx === 0 ? "M" : "L") + p[0].toFixed(1) + " " + p[1].toFixed(1);
          }).join(" ") + " Z";
        }).join(" ");
        var isSelected = gc.fips === selectedFips;
        var suffix = coreMapMetric === "bottleneck"
          ? " · " + bInfo.label + " (+" + integer(value) + ")"
          : (coreMapMetric === "lift"
            ? " · " + (lift >= 0 ? "+" : "") + lift.toFixed(1) + "% lift (+" + integer(value) + ")"
            : " · +" + integer(value) + " homes calculated");
        var label = (county ? county.name : gc.name) + suffix;
        var basePoly =
          '<path class="county-poly' + (isSelected ? " selected" : "") + '" role="button" aria-label="' + escapeHtml(label) +
          '" data-fips="' + gc.fips + '" d="' + d + '" fill="' + fill +
          '" stroke="#ffffff" stroke-width="0.9"><title>' + escapeHtml(label) + "</title></path>" +
          '<path class="map-hit" data-fips="' + gc.fips + '" d="' + d + '" fill="transparent"><title>' + escapeHtml(label) + "</title></path>";
        if (isSelected) {
          selectedPathHtml = '<path d="' + d + '" fill="none" stroke="#112238" stroke-width="2.8" pointer-events="none"></path>';
        }
        return basePoly;
      }).join("");

      mapStage.innerHTML =
        '<svg viewBox="0 0 ' + width + " " + height + '" role="group" aria-label="Choropleth map of ' + escapeHtml(result.name) + ' counties, colored by ' + escapeHtml(chosenScenario.label) + '">' +
        '<rect width="100%" height="100%" rx="10" fill="#f4f1e8"></rect>' +
        paths +
        selectedPathHtml +
        "</svg>";
    } else {
      /* Fallback to interior gazetteer points if polygon archive unavailable */
      var points = pointsFor(stateCode);
      if (!points.length) {
        mapStage.textContent = "No county geometry available for this state.";
        return;
      }
      var pBox = boundsOf(points);
      var hull = convexHull(points.map(function (point) { return project(point, pBox, width, height); }));
      var hullPath = hull.map(function (pair, index) {
        return (index === 0 ? "M" : "L") + pair[0].toFixed(1) + " " + pair[1].toFixed(1);
      }).join(" ") + " Z";
      var circles = points.map(function (point) {
        var county = countyByFips(point.fips);
        var pxy = project(point, pBox, width, height);
        var value = metricOf(county);
        var fill = choroplethColor(value, maxMetric);
        var radius = 5 + 9 * Math.sqrt((county ? county.housing_units : 1) / result.housing_units);
        var selected = point.fips === selectedFips;
        var label = (county ? county.name : point.name) + ", " + integer(value) + " calculated";
        return '<circle data-fips="' + point.fips + '" cx="' + pxy[0].toFixed(1) +
          '" cy="' + pxy[1].toFixed(1) + '" r="' + radius.toFixed(1) + '" fill="' + fill +
          '" stroke="' + (selected ? "#112238" : "#1c2430") + '" stroke-width="' + (selected ? 2.5 : 0.6) +
          '"><title>' + escapeHtml(label) + "</title></circle>" +
          '<circle class="map-hit" data-fips="' + point.fips + '" cx="' + pxy[0].toFixed(1) +
          '" cy="' + pxy[1].toFixed(1) + '" r="12" fill="transparent"><title>' + escapeHtml(label) + "</title></circle>";
      }).join("");
      mapStage.innerHTML =
        '<svg viewBox="0 0 ' + width + " " + height + '" role="group" aria-label="Map of ' + escapeHtml(result.name) + ' counties">' +
        '<rect width="100%" height="100%" fill="#f4f1e8"></rect>' +
        '<path d="' + hullPath + '" fill="#e7f0e4" stroke="#0f6b4e" stroke-width="1.5"></path>' +
        circles +
        "</svg>";
    }

    bindMapKeys();
    bindRoving(mapStage, ".county-poly[data-fips], circle[data-fips]:not(.map-hit)");
    renderCountySelect();
    renderCountyDetail(selectedFips ? countyByFips(selectedFips) : null);
    renderCorePin();
  }

  function statePolygonsGroup(code, localBox, originX, originY, drawW, drawH) {
    var counties = geoCountiesFor(code);
    if (!counties.length) return "";
    var midLat = ((localBox.minY + localBox.maxY) / 2) * Math.PI / 180;
    var xspan = Math.max(0.05, (localBox.maxX - localBox.minX) * Math.cos(midLat));
    var yspan = Math.max(0.05, localBox.maxY - localBox.minY);
    var scale = Math.min(drawW / xspan, drawH / yspan);
    var ox = originX + (drawW - xspan * scale) / 2;
    var oy = originY + (drawH - yspan * scale) / 2;
    var active = code === stateCode;
    var stMeta = stateCatalog.filter(function (s) { return s.code === code; })[0];
    var fill = active ? "#0e6e5c" : (stMeta && stMeta.tier === 1 ? "#c7dcf2" : "#e3dfd4");
    var stroke = active ? "#112238" : "#516173";
    var countyPaths = counties.map(function (c) {
      var d = (c.rings || []).map(function (ring) {
        return ring.map(function (pt, idx) {
          var px = ox + (pt[0] - localBox.minX) * Math.cos(midLat) * scale;
          var py = oy + (localBox.maxY - pt[1]) * scale;
          return (idx === 0 ? "M" : "L") + px.toFixed(1) + " " + py.toFixed(1);
        }).join(" ") + " Z";
      }).join(" ");
      return '<path class="county-poly" d="' + d + '" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + (active ? "0.9" : "0.5") + '"></path>';
    }).join("");
    var stBox = boundsOfRings(counties);
    var stMidLon = (stBox.minX + stBox.maxX) / 2;
    var stMidLat = (stBox.minY + stBox.maxY) / 2;
    var cx = ox + (stMidLon - localBox.minX) * Math.cos(midLat) * scale;
    var cy = oy + (localBox.maxY - stMidLat) * scale;
    var titleText = stMeta ? (stMeta.name + " (Tier " + stMeta.tier + ")") : code;
    return '<g role="button" tabindex="0" data-state="' + code + '" aria-label="Select ' + escapeHtml(titleText) + '">' +
      countyPaths +
      '<rect x="' + (cx - 14).toFixed(1) + '" y="' + (cy - 9).toFixed(1) + '" width="28" height="18" rx="4" fill="' + (active ? "#112238" : "rgba(255,255,255,0.88)") + '"></rect>' +
      '<text x="' + cx.toFixed(1) + '" y="' + (cy + 4).toFixed(1) + '" text-anchor="middle" font-size="11" font-weight="700" font-family="sans-serif" fill="' + (active ? "#ffffff" : "#112238") + '">' + code + "</text>" +
      "<title>" + escapeHtml(titleText) + "</title></g>";
  }

  function renderNationMap() {
    mapTitle.textContent = "All 11 Challenge States";
    var width = 800;
    var height = 460;
    if (geoAllDoc && geoAllDoc.states) {
      var insetCodes = { HI: true, CT: true, RI: true, NH: true };
      var mainlandCounties = [];
      Object.keys(geoAllDoc.states).forEach(function (code) {
        if (!insetCodes[code]) mainlandCounties = mainlandCounties.concat(geoAllDoc.states[code]);
      });
      var mainBox = boundsOfRings(mainlandCounties);
      var shapes = Object.keys(geoAllDoc.states).filter(function (code) { return !insetCodes[code]; }).map(function (code) {
        return statePolygonsGroup(code, mainBox, 24, 18, width - 220, height - 36);
      }).join("");
      shapes += statePolygonsGroup("HI", boundsOfRings(geoCountiesFor("HI")), 26, 322, 142, 106);
      [
        { code: "NH", x: 616, y: 36, w: 156, h: 112 },
        { code: "CT", x: 616, y: 168, w: 156, h: 102 },
        { code: "RI", x: 616, y: 290, w: 156, h: 112 },
      ].forEach(function (cell) {
        var cList = geoCountiesFor(cell.code);
        if (cList.length) {
          shapes += statePolygonsGroup(cell.code, boundsOfRings(cList), cell.x, cell.y, cell.w, cell.h);
        }
      });
      mapStage.innerHTML =
        '<svg viewBox="0 0 800 460" role="group" aria-label="Cartographic map of the eleven challenge states. Hawaii and New England states are inset for legibility.">' +
        '<rect width="100%" height="100%" rx="10" fill="#f4f1e8"></rect>' +
        '<rect x="16" y="300" width="164" height="142" rx="8" fill="#ffffff" stroke="#d9d0c2"></rect>' +
        '<text x="26" y="318" font-size="11" font-weight="700" font-family="sans-serif" fill="#4f5862">HAWAII (TIER 1)</text>' +
        '<rect x="604" y="16" width="180" height="426" rx="8" fill="#ffffff" stroke="#d9d0c2"></rect>' +
        '<text x="616" y="34" font-size="11" font-weight="700" font-family="sans-serif" fill="#4f5862">NEW ENGLAND ZOOM</text>' +
        shapes +
        "</svg>";
      bindMapKeys();
      bindRoving(mapStage, "[data-state]");
      countyDetail.hidden = true;
      return;
    }
    countyDetail.hidden = true;
  }

  function bindRoving(container, selector) {
    var nodes = Array.prototype.slice.call(container.querySelectorAll(selector));
    var unique = [];
    var seen = {};
    nodes.forEach(function (node) {
      var key = node.getAttribute("data-fips") || node.getAttribute("data-state");
      if (!key || seen[key]) return;
      seen[key] = true;
      unique.push(node);
    });
    unique.forEach(function (node, index) {
      var key = node.getAttribute("data-fips");
      var isSel = key && key === selectedFips;
      node.tabIndex = isSel || (!selectedFips && index === 0) ? 0 : -1;
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
        renderCounties();
        loadInsights();
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
        '<div class="table-wrap" role="region" tabindex="0" aria-label="Cross-check table for ' + escapeHtml(code) + '">' +
        "<table><thead><tr><th>Scenario</th><th>Full</th><th>Hidden parcels</th><th>Error</th><th>State median screen</th><th>Error</th></tr></thead><tbody>";
      Object.keys(names).forEach(function (id) {
        var block = item.scenarios[id];
        html += "<tr><td>" + names[id] + "</td><td>" + tagged(block.imputed_parcels.full, "calculated", integer) +
          "</td><td>" + tagged(block.imputed_parcels.other, "calculated", integer) +
          "</td><td>" + errorText(block.imputed_parcels) +
          "</td><td>" + tagged(block.state_screen.other, "calculated", integer) +
          "</td><td>" + errorText(block.state_screen) + "</td></tr>";
      });
      html += "</tbody></table></div>";
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
    if (studioStateSelect) studioStateSelect.value = mapScope === "nation" ? "ALL" : stateCode;
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
    selectedFips = null;
    updateOverrideBadge();
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

  function renderBriefingStrip() {
    if (!briefingStripMount || !insightsDoc) return;
    var aff = insightsDoc.affordability_screen || {};
    var protos = aff.prototypes || [];
    var aduProto = protos[0];
    var mmProto = protos[1] || protos[0];
    var stancesWrap = insightsDoc.priority_stances || {};
    var stances = stancesWrap.stances || [];
    var chosenStance = stances[0];
    stances.forEach(function (s) {
      if (s.id === activeStanceId) chosenStance = s;
    });
    var topRank = chosenStance && chosenStance.rankings && chosenStance.rankings[0];
    var cardDoc = insightsDoc.official_data_card || {};
    var cObs = cardDoc.observed || {};
    var cComp = cardDoc.completeness || {};

    var aduLine = aduProto
      ? "$" + integer(aduProto.metrics.breakeven_rent_before) + " → <strong>$" + integer(aduProto.metrics.breakeven_rent_after) + "/mo</strong> (" + escapeHtml(aduProto.lowest_ami_band_after) + ")"
      : "—";
    var mmLine = mmProto
      ? "$" + integer(mmProto.metrics.breakeven_rent_before) + " → <strong>$" + integer(mmProto.metrics.breakeven_rent_after) + "/mo</strong> (" + escapeHtml(mmProto.lowest_ami_band_after) + ")"
      : "—";

    var stanceMiniBtns = stances.map(function (s) {
      var on = chosenStance && s.id === chosenStance.id;
      return '<button type="button" class="mini-stance-pill' + (on ? " active" : "") + '" aria-pressed="' + (on ? "true" : "false") + '" data-mini-stance="' + escapeHtml(s.id) + '">' +
        escapeHtml(s.label.split("&")[0].trim()) + "</button>";
    }).join("");

    briefingStripMount.innerHTML =
      '<article class="briefing-tile">' +
        '<span class="step-kicker">HUD AMI Breakeven (' + escapeHtml(aff.geography_label || stateCode) + ')</span>' +
        "<p class='tile-main'>Backyard ADU: " + aduLine + " " + badge("calculated") + "</p>" +
        "<p class='help'>" + escapeHtml(mmProto ? mmProto.label : "Multiplex") + ": " + mmLine + "</p>" +
      "</article>" +
      '<article class="briefing-tile">' +
        '<span class="step-kicker">Stakeholder Priority Stance</span>' +
        "<p class='tile-main'>" + (topRank ? ("#1 " + escapeHtml(topRank.label) + " (" + oneDecimal(topRank.scores.composite_score) + " pts)") : "—") +
        (chosenStance && chosenStance.too_close_to_call ? ' <span class="badge-uncertain">≤3 pt tie</span>' : "") + "</p>" +
        '<div class="mini-stance-row" role="group" aria-label="Quick priority stance">' + stanceMiniBtns + "</div>" +
      "</article>" +
      '<article class="briefing-tile">' +
        '<span class="step-kicker">Official State GIS &amp; Workforce</span>' +
        "<p class='tile-main'>" + escapeHtml(cardDoc.portal_name || stateCode) + " · <strong>" +
        escapeHtml(String(cComp.benchmark_completeness || 0)) + "% → " + escapeHtml(String(cComp.extended_completeness || 0)) + "%</strong> " + badge("calculated") + "</p>" +
        "<p class='help'>" + integer(cObs.parcel_records_observed) + " parcels · " + integer(cObs.ntad_transit_stops) + " transit stops " + badge("observed") + "</p>" +
      "</article>";

    briefingStripMount.querySelectorAll("[data-mini-stance]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        activeStanceId = btn.getAttribute("data-mini-stance") || "balanced";
        renderBriefingStrip();
        if (insightsMount) renderInsights();
      });
    });
  }

  function renderInsights() {
    renderBriefingStrip();
    if (!insightsMount) return;
    if (!insightsDoc) {
      insightsMount.innerHTML = '<p class="help">Loading official data hub, HUD AMI breakeven rents, and code screen…</p>';
      return;
    }
    var aff = insightsDoc.affordability_screen;
    var obsCtx = aff.observed_context || {};
    var codeCap = insightsDoc.building_code_and_capacity;
    var stairImp = codeCap.single_stair_impact;
    var wf = codeCap.workforce_capacity;
    var wfObs = wf.observed_bls;
    var wfAbs = wf.absorption_metrics;
    var stancesWrap = insightsDoc.priority_stances;
    var stances = stancesWrap.stances || [];
    var chosenStance = stances[0];
    stances.forEach(function (s) {
      if (s.id === activeStanceId) chosenStance = s;
    });
    var cardDoc = insightsDoc.official_data_card;
    var cObs = cardDoc.observed;
    var cComp = cardDoc.completeness;
    var mktPct = Math.round(Number(cObs.vacant_market_available_share || 0) * 100);
    var seasPct = Math.round(Number(cObs.vacant_seasonal_share || 0) * 100);
    var othPct = Math.max(0, 100 - mktPct - seasPct);

    var amiPills = (aff.ami_bands || []).map(function (b) {
      return '<div class="ami-pill">' +
        '<span class="ami-band">' + escapeHtml(b.label) + "</span>" +
        '<strong>$' + integer(b.max_monthly_housing_budget) + "/mo</strong> " + badge("calculated") +
        '<span class="ami-inc">≤$' + integer(b.annual_income_ceiling) + "/yr</span>" +
        "</div>";
    }).join("");

    var protoRows = (aff.prototypes || []).map(function (p) {
      var m = p.metrics;
      var sav = Number(m.monthly_rent_savings || 0);
      return "<tr>" +
        "<td><strong>" + escapeHtml(p.label) + "</strong><div class='help'>" + escapeHtml(p.lever_note) + "</div></td>" +
        "<td>" + integer(m.unit_sqft) + " sq ft " + badge("assumed") + "</td>" +
        "<td>$" + integer(m.breakeven_rent_before) + "/mo " + badge("calculated") +
          "<div class='ami-chip before'>" + escapeHtml(p.lowest_ami_band_before) + "</div></td>" +
        "<td><strong>$" + integer(m.breakeven_rent_after) + "/mo</strong> " + badge("calculated") +
          "<div class='ami-chip after'>" + escapeHtml(p.lowest_ami_band_after) + "</div></td>" +
        "<td>" + (sav > 0 ? "−$" + integer(sav) + "/mo" : "$0/mo") + " " + badge("calculated") + "</td>" +
        "</tr>";
    }).join("");

    var fmrText = obsCtx.hud_fmr_2br
      ? " · HUD FY2026 2BR FMR $" + integer(obsCtx.hud_fmr_2br) + "/mo " + badge("observed")
      : "";

    var stanceButtons = stances.map(function (s) {
      var on = chosenStance && s.id === chosenStance.id;
      return '<button type="button" class="stance-btn' + (on ? " active" : "") + '" aria-pressed="' + (on ? "true" : "false") + '" data-stance-id="' + escapeHtml(s.id) + '">' +
        escapeHtml(s.label) + "</button>";
    }).join("");

    var stanceRanks = chosenStance ? (chosenStance.rankings || []).map(function (r, idx) {
      var sc = r.scores;
      var w = Math.max(4, Math.min(100, Number(sc.composite_score || 0)));
      return '<div class="stance-row">' +
        '<div class="stance-rank-head">' +
          '<span><strong>#' + (idx + 1) + " · " + escapeHtml(r.label) + "</strong></span>" +
          '<span><strong>' + oneDecimal(sc.composite_score) + " pts</strong> " + badge("calculated") +
          " · +" + integer(sc.net_completions_5yr) + " homes</span>" +
        "</div>" +
        '<div class="stance-bar-track" aria-hidden="true"><i style="width:' + w.toFixed(1) + '%"></i></div>' +
        "</div>";
    }).join("") : "";

    var wts = chosenStance ? chosenStance.weights : {};
    var weightLine = chosenStance
      ? "Value-judgment weights: Supply " + Math.round((wts.supply || 0) * 100) + "% " + badge("assumed") +
        " · Affordability " + Math.round((wts.affordability || 0) * 100) + "% " + badge("assumed") +
        " · Transit &amp; compact land " + Math.round((wts.compact_transit || 0) * 100) + "% " + badge("assumed") +
        " · Fast / zero-backfill " + Math.round((wts.speed_fiscal || 0) * 100) + "% " + badge("assumed")
      : "";

    var matrixHtml = "";
    if (dataSourcesDoc && dataSourcesDoc.states) {
      var stateRows = dataSourcesDoc.states.map(function (st) {
        var om = st.observed_metrics;
        var cp = st.completeness;
        return "<tr" + (st.code === stateCode ? ' class="selected-row"' : "") + ">" +
          "<td><strong>" + escapeHtml(st.code) + "</strong> · " + escapeHtml(st.name) + "</td>" +
          '<td><a href="' + escapeHtml(st.portal_url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(st.portal_name) + "</a></td>" +
          "<td>" + integer(om.parcel_records_observed) + " parcels · " + integer(om.zoning_or_landuse_records) + " zoning/LU " + badge("observed") + "</td>" +
          "<td>" + integer(om.ntad_transit_stops) + " stops " + badge("observed") + "</td>" +
          "<td>" + oneDecimal(om.bls_jobs_latest_thousands) + "k (" + signedPercent(om.bls_jobs_change_pct) + ") " + badge("observed") + "</td>" +
          "<td>" + Math.round(om.vacant_market_available_share * 100) + "% mkt / " + Math.round(om.vacant_seasonal_share * 100) + "% seasonal " + badge("observed") + "</td>" +
          "<td>" + cp.benchmark_completeness + "% → <strong>" + cp.extended_completeness + "%</strong> " + badge("calculated") + "</td>" +
          "</tr>";
      }).join("");

      var famRows = (dataSourcesDoc.handbook_families || []).map(function (f) {
        return "<tr><td><strong>" + escapeHtml(f.name) + "</strong></td><td>" +
          escapeHtml(f.vintage) + "</td><td>" + escapeHtml(f.license) + "</td><td><span class='pill t1'>" +
          escapeHtml(f.status) + "</span></td></tr>";
      }).join("");

      matrixHtml =
        '<details class="hub-matrix-details">' +
          '<summary>View all 11 official state GIS portals (<code>data/DATA_SOURCES.md</code>) &amp; 10 Handbook dataset families</summary>' +
          '<div class="hub-matrix-body">' +
            '<div class="table-wrap" role="region" tabindex="0" aria-label="All eleven official state GIS portals">' +
              "<table><thead><tr><th>State</th><th>Official Portal</th><th>Observed GIS Records</th><th>USDOT Stops</th><th>BLS Workforce</th><th>ACS B25004 Vacancy</th><th>Coverage</th></tr></thead><tbody>" +
              stateRows + "</tbody></table>" +
            "</div>" +
            "<h4>All 10 Challenge Handbook &amp; Starter Dataset Families</h4>" +
            '<div class="table-wrap" role="region" tabindex="0" aria-label="Integrated Handbook dataset families">' +
              "<table><thead><tr><th>Dataset Family</th><th>Vintage Loaded</th><th>License / Terms</th><th>Status</th></tr></thead><tbody>" +
              famRows + "</tbody></table>" +
            "</div>" +
          "</div>" +
        "</details>";
    }

    insightsMount.innerHTML =
      '<article class="insight-card">' +
        '<div class="panel-head">' +
          "<div>" +
            '<p class="step-kicker">1 · Household Affordability &amp; Building-Code Modernization</p>' +
            "<h3>" + escapeHtml(aff.geography_label) + " — HUD AMI Breakeven Rent &amp; Single-Stair Screen</h3>" +
          "</div>" +
          (insightsDoc.selected_county_fips
            ? '<button type="button" class="btn-pill" id="insights-clear-county">Show statewide ' + escapeHtml(insightsDoc.state_name) + "</button>"
            : "") +
        "</div>" +
        '<p class="help">Observed median income <strong>$' + integer(obsCtx.median_income) + "</strong> " + badge("observed") +
          " · Median gross rent <strong>$" + integer(obsCtx.median_rent) + "/mo</strong> " + badge("observed") +
          fmrText + ". " + escapeHtml(aff.scope_note) + "</p>" +
        '<label class="stair-toggle" for="single-stair-toggle">' +
          '<input type="checkbox" id="single-stair-toggle"' + (singleStairOn ? " checked" : "") + ">" +
          '<span><strong>Include Single-Stair 6-Story Building Code Reform</strong> — allows one pressurized stair on sprinklered 3–6 story blocks (≤4 homes/floor), unlocking <strong>+' +
          integer(stairImp.incremental_homes_from_single_stair) + " extra package homes</strong> in " + escapeHtml(insightsDoc.state_name) + " " + badge("calculated") + "</span>" +
        "</label>" +
        '<div class="ami-grid" aria-label="HUD AMI monthly housing budgets">' + amiPills + "</div>" +
        '<div class="table-wrap" role="region" tabindex="0" aria-label="Before and after reform breakeven monthly rent by prototype">' +
          "<table><thead><tr><th>Infill Prototype</th><th>Size</th><th>Before Reform Breakeven</th><th>After Reform Breakeven</th><th>Monthly Cost Relief</th></tr></thead><tbody>" +
          protoRows + "</tbody></table>" +
        "</div>" +
        '<div class="workforce-strip">' +
          "<div><strong>BLS Construction Workforce (" + escapeHtml(insightsDoc.state) + "):</strong> " +
            oneDecimal(wfObs.bls_jobs_latest_thousands) + "k jobs (" + signedPercent(wfObs.bls_jobs_change_2020_2025_pct) + " vs 2020) " + badge("observed") +
            " · Materials PPI +" + oneDecimal(cObs.national_ppi_inflation_2020_latest_pct) + "% (2020–2025) " + badge("observed") + "</div>" +
          "<div><strong>Workforce Absorption:</strong> +" + oneDecimal(wfAbs.incremental_homes_per_1k_workers) +
            " added homes / 1,000 workers / yr (vs " + oneDecimal(wfAbs.baseline_homes_per_1k_workers) + " baseline) " + badge("calculated") +
            " · <span class='wf-badge'>" + escapeHtml(wf.labor_strain_tier) + "</span></div>" +
        "</div>" +
      "</article>" +

      '<article class="insight-card">' +
        '<p class="step-kicker">2 · Value Judgments vs. Model Outputs (3-Point Caution Band)</p>' +
        "<h3>Stakeholder Priority Stances — Which Standalone Reform Ranks First?</h3>" +
        '<p class="help">' + escapeHtml(stancesWrap.methodology_note) + "</p>" +
        '<div class="stance-bar" role="group" aria-label="Stakeholder priority stances">' + stanceButtons + "</div>" +
        (chosenStance
          ? '<div class="callout stance-callout">' +
              "<p><strong>" + escapeHtml(chosenStance.label) + ":</strong> " + escapeHtml(chosenStance.summary) + "</p>" +
              "<p>" + (chosenStance.too_close_to_call ? '<span class="badge-uncertain">Too close to call (≤3 pts)</span> ' : "") +
              escapeHtml(chosenStance.caution_note) + "</p>" +
              '<p class="help">' + weightLine + "</p>" +
            "</div>" +
            '<div class="stance-ranks">' + stanceRanks + "</div>"
          : "") +
      "</article>" +

      '<article class="insight-card">' +
        '<p class="step-kicker">3 · Official Hackathon Data Coverage (' + escapeHtml(insightsDoc.state_name) + ')</p>' +
        '<h3><a href="' + escapeHtml(cardDoc.portal_url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(cardDoc.portal_name) + "</a></h3>" +
        "<p>" + escapeHtml(cardDoc.headline_finding) + "</p>" +
        '<div class="hub-kpi-grid">' +
          '<div class="hub-kpi"><span>Data Completeness</span><strong>' + cComp.benchmark_completeness + "% → " + cComp.extended_completeness + "%</strong> " + badge("calculated") + "<small>Benchmark Tier " + cComp.tier + " vs. Extended Hub</small></div>" +
          '<div class="hub-kpi"><span>Observed GIS Features</span><strong>' + integer(cObs.parcel_records_observed) + "</strong> " + badge("observed") + "<small>Parcels + " + integer(cObs.zoning_or_landuse_records) + " zoning/land-use records</small></div>" +
          '<div class="hub-kpi"><span>Transit &amp; Footprints</span><strong>' + integer(cObs.ntad_transit_stops) + " stops</strong> " + badge("observed") + "<small>" + (cObs.rail_stations + cObs.brt_stations) + " major rail/BRT · " + integer(cObs.building_footprints) + " footprints</small></div>" +
          '<div class="hub-kpi"><span>ACS B25004 Vacancy Split</span><strong>' + mktPct + "% market</strong> " + badge("observed") + "<small>" + seasPct + "% seasonal · " + othPct + "% other (" + integer(cObs.vacant_total) + " vacant)</small>" +
            '<div class="vac-bar" aria-hidden="true"><i class="vac-mkt" style="width:' + mktPct + '%"></i><i class="vac-seas" style="width:' + seasPct + '%"></i><i class="vac-oth" style="width:' + othPct + '%"></i></div>' +
          "</div>" +
        "</div>" +
        matrixHtml +
      "</article>";

    var stairBox = document.getElementById("single-stair-toggle");
    if (stairBox) {
      stairBox.addEventListener("change", function () {
        singleStairOn = !!stairBox.checked;
        updateOverrideBadge();
        loadInsights();
      });
    }
    var clearCountyBtn = document.getElementById("insights-clear-county");
    if (clearCountyBtn) {
      clearCountyBtn.addEventListener("click", function () {
        selectedFips = null;
        if (result) renderMap();
        loadInsights();
      });
    }
    insightsMount.querySelectorAll("[data-stance-id]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        activeStanceId = btn.getAttribute("data-stance-id") || "balanced";
        renderInsights();
      });
    });
  }

  function loadInsights() {
    var iid = ++insightsRequestId;
    var payload = {
      state: stateCode,
      overrides: overrides,
      reforms: reformsPayload(),
      single_stair: singleStairOn,
    };
    if (selectedFips) payload.county = selectedFips;
    post("/api/insights", payload)
      .then(function (doc) {
        if (iid !== insightsRequestId) return;
        insightsDoc = doc;
        renderInsights();
      })
      .catch(function () {
        if (iid !== insightsRequestId) return;
        if (insightsMount) insightsMount.innerHTML = '<p class="help">Could not load insights for this selection.</p>';
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
    loadInsights();
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

  function activateTab(tab, preserveDepth) {
    if (!preserveDepth && studioDepth === "briefing") {
      setStudioDepth("audit", true);
    }
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
    if (tab.getAttribute("data-tab") === "insights") {
      if (insightsDoc) renderInsights();
      else loadInsights();
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

  /* Studio Depth Buttons & Quick Prompts */
  document.querySelectorAll("[data-depth-btn]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = btn.getAttribute("data-depth-btn");
      setStudioDepth(target);
      if (target === "markup") {
        var ribbon = document.getElementById("studio-markup-ribbon");
        if (ribbon && ribbon.scrollIntoView) ribbon.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } else if (target === "audit") {
        var shell = document.getElementById("analysis-shell");
        if (shell && shell.scrollIntoView) shell.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  document.querySelectorAll("[data-depth-jump]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = btn.getAttribute("data-depth-jump");
      setStudioDepth(target);
      var dest = target === "markup" ? document.getElementById("panel-insights") : document.getElementById("analysis-shell");
      if (dest && dest.scrollIntoView) dest.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  var collapseBtn = document.getElementById("collapse-to-briefing");
  if (collapseBtn) {
    collapseBtn.addEventListener("click", function () {
      setStudioDepth("briefing", true);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  /* Command Bar State Quick-Jump & Drawers */
  if (studioStateSelect) {
    studioStateSelect.addEventListener("change", function () {
      var val = studioStateSelect.value;
      if (val === "ALL") {
        mapScope = "nation";
        selectedFips = null;
        renderMap();
        return;
      }
      if (!val) return;
      mapScope = "state";
      selectedFips = null;
      selectState(val);
    });
  }
  var btnToggleStates = document.getElementById("toggle-states-drawer");
  if (btnToggleStates) {
    btnToggleStates.addEventListener("click", function () {
      if (statesDrawer && !statesDrawer.hidden) closeDrawers();
      else openDrawer("states");
    });
  }
  var btnCloseStates = document.getElementById("close-states-drawer");
  if (btnCloseStates) btnCloseStates.addEventListener("click", closeDrawers);

  var btnToggleAssump = document.getElementById("toggle-assumptions-drawer");
  if (btnToggleAssump) {
    btnToggleAssump.addEventListener("click", function () {
      if (assumptionsDrawer && !assumptionsDrawer.hidden) closeDrawers();
      else openDrawer("assumptions");
    });
  }
  var inlineTuneBtn = document.getElementById("inline-tune-btn");
  if (inlineTuneBtn) {
    inlineTuneBtn.addEventListener("click", function () { openDrawer("assumptions"); });
  }
  var btnCloseAssump = document.getElementById("close-assumptions-drawer");
  if (btnCloseAssump) btnCloseAssump.addEventListener("click", closeDrawers);
  if (studioBackdrop) studioBackdrop.addEventListener("click", closeDrawers);

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      if ((statesDrawer && !statesDrawer.hidden) || (assumptionsDrawer && !assumptionsDrawer.hidden)) {
        event.preventDefault();
        closeDrawers();
      }
    }
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

  var openMarkupPresets = document.getElementById("open-markup-presets");
  if (openMarkupPresets) {
    openMarkupPresets.addEventListener("click", function () {
      setStudioDepth("markup", true);
      var rib = document.getElementById("studio-markup-ribbon");
      if (rib && rib.scrollIntoView) rib.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  var openInsightsBtn = document.getElementById("open-insights");
  if (openInsightsBtn) {
    openInsightsBtn.addEventListener("click", function () {
      setStudioDepth("markup", true);
      var insTab = document.getElementById("tab-insights");
      var insPanel = document.getElementById("panel-insights");
      if (insTab) activateTab(insTab, true);
      if (insPanel && insPanel.scrollIntoView) {
        insPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  var openPortability = document.getElementById("open-portability");
  if (openPortability) {
    openPortability.addEventListener("click", function () {
      setStudioDepth("audit", true);
      if (moreList && moreList.hidden) {
        moreList.hidden = false;
        if (moreBtn) moreBtn.setAttribute("aria-expanded", "true");
      }
      var crossTab = document.getElementById("tab-cross");
      var crossPanel = document.getElementById("panel-cross");
      if (crossTab) activateTab(crossTab, true);
      if (crossPanel && crossPanel.scrollIntoView) {
        crossPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  var openAuditMath = document.getElementById("open-audit-math");
  if (openAuditMath) {
    openAuditMath.addEventListener("click", function () {
      setStudioDepth("audit", true);
      var mathTab = document.getElementById("tab-math");
      var mathPanel = document.getElementById("panel-math");
      if (mathTab) activateTab(mathTab, true);
      if (mathPanel && mathPanel.scrollIntoView) {
        mathPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  var skipMapLink = document.querySelector(".skip-map");
  if (skipMapLink) {
    skipMapLink.addEventListener("click", function () {
      setStudioDepth("audit", true);
      var cTab = document.getElementById("tab-counties");
      if (cTab) activateTab(cTab, true);
    });
  }

  var countyPick = document.getElementById("county-select");
  if (countyPick) {
    countyPick.addEventListener("change", function () {
      selectedFips = countyPick.value;
      mapScope = "state";
      if (studioStateSelect) studioStateSelect.value = stateCode;
      renderMap();
      renderCounties();
      loadInsights();
    });
  }

  document.getElementById("reset").addEventListener("click", function () {
    overrides = {};
    singleStairOn = false;
    REFORMS.forEach(function (id) {
      reformOn[id] = true;
      reformWeight[id] = 1;
    });
    updateOverrideBadge();
    renderReformMix();
    renderSliders();
    simulate().catch(fail);
  });

  document.getElementById("map-back").addEventListener("click", function () {
    mapScope = "nation";
    selectedFips = null;
    if (studioStateSelect) studioStateSelect.value = "ALL";
    renderMap();
    loadInsights();
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

  setStudioDepth(studioDepth, true);
  renderReformMix();
  renderCorePresets();
  Promise.all([
    request("/api/states"),
    request("/api/map"),
    request("/api/adu-compare?state=PA"),
    request("/api/data-sources").catch(function () { return null; }),
    request("/api/geo").catch(function () { return null; })
  ])
    .then(function (payloads) {
      mapDoc = payloads[1];
      aduCompareCache.PA = payloads[2];
      aduCompare = payloads[2];
      dataSourcesDoc = payloads[3];
      geoAllDoc = payloads[4];
      fillAduFeeNote();
      renderStates(payloads[0].states);
      var known = (payloads[0].states || []).some(function (row) { return row.code === stateCode; });
      return selectState(known ? stateCode : "PA");
    })
    .catch(fail);
})();
