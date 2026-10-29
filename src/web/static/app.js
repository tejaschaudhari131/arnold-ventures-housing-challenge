/* Stateframe client. Recalculates by calling the equation server.
   Nothing on this page stores a precomputed grid. */
(function () {
  "use strict";

  var ORDER = ["baseline", "adu", "missing_middle", "tod", "parking", "fees", "combined"];
  var stateCode = "PA";
  var scenarioId = "adu";
  var parameters = [];
  var overrides = {};
  var result = null;
  var timer = null;
  var requestId = 0;

  var statusEl = document.getElementById("status");
  var stateList = document.getElementById("state-list");
  var headline = document.getElementById("headline");
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
    return n.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 0 });
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

  function formatSetting(spec, value) {
    var n = Number(value);
    var step = Number(stepFor(spec));
    var digits = 0;
    if (step > 0 && step < 1) {
      digits = Math.min(4, Math.ceil(-Math.log10(step)));
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

  function renderStates(catalog) {
    stateList.innerHTML = "";
    catalog.forEach(function (state) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "state-btn" + (state.code === stateCode ? " active" : "");
      button.setAttribute("aria-pressed", state.code === stateCode ? "true" : "false");
      var score = Math.round(Number(state.completeness) * 100);
      button.innerHTML =
        "<strong>" + state.name + "</strong>" +
        '<span class="pill ' + (state.tier === 1 ? "t1" : "t2") + '">Tier ' + state.tier + "</span>" +
        "<span>" + integer(state.housing_units) + " homes · completeness " + score + "%</span>" +
        '<span class="meter" aria-hidden="true"><i style="width:' + score + '%"></i></span>';
      button.addEventListener("click", function () {
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
        var wrap = document.createElement("div");
        wrap.className = "slider";
        var label = document.createElement("label");
        var title = document.createElement("span");
        title.textContent = spec.label;
        var value = document.createElement("span");
        var current = sliderValue(spec);
        value.textContent = formatSetting(spec, current);
        label.appendChild(title);
        label.appendChild(value);
        var input = document.createElement("input");
        input.type = "range";
        input.min = spec.low;
        input.max = spec.high;
        input.step = stepFor(spec);
        input.value = String(current);
        input.setAttribute("aria-label", spec.label);
        function onSlide() {
          var next = Number(input.value);
          value.textContent = formatSetting(spec, next);
          if (Math.abs(next - Number(spec.central)) < Number(input.step) / 2) {
            delete overrides[spec.name];
          } else {
            overrides[spec.name] = next;
          }
          schedule();
        }
        input.addEventListener("input", onSlide);
        input.addEventListener("change", onSlide);
        var hint = document.createElement("p");
        hint.className = "hint";
        hint.textContent = spec.help || ("Published band " + oneDecimal(spec.low) + " to " + oneDecimal(spec.high) + ".");
        wrap.appendChild(label);
        wrap.appendChild(input);
        wrap.appendChild(hint);
        details.appendChild(wrap);
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
    headline.innerHTML =
      card("Baseline completions", integer(result.baseline_completions_5yr), "Five-year units added under current rules") +
      card("Package, net new", integer(result.scenarios.combined.incremental_completions), signedPercent(lift) + " versus baseline") +
      card("Walkshed", oneDecimal(result.walkshed_sqmi) + " sq mi", "Major transit stops, after overlap") +
      card("Lot screen", Math.round(result.lot_feasible_share * 100) + "%", "Single-family lots that can hold a 600 sq ft ADU");
  }

  function card(label, value, sub) {
    return '<article class="stat"><div class="k">' + label + '</div><div class="v">' + value + '</div><div class="s">' + sub + "</div></article>";
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
      tr.innerHTML =
        "<td>" + row.label + (row.cap_binding ? " · capped" : "") + "</td>" +
        "<td>" + integer(row.permits_5yr) + "</td>" +
        "<td>" + integer(row.completions_5yr) + "</td>" +
        "<td>" + net + "</td>" +
        "<td>" + integer(row.annualized_completions) + "</td>" +
        "<td>" + lift + "</td>";
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
    var extra = "";
    if (scenarioId === "combined") {
      var c = result.components;
      extra = "<p>Inside the package: ADUs " + integer(c.combined_adu) +
        ", missing middle " + integer(c.combined_mm) +
        ", TOD " + integer(c.combined_tod) +
        ", parking " + integer(c.combined_parking) +
        ", fees " + integer(c.combined_fees) +
        ". Those five parts add to the package total. Fee and parking savings inside the zoning pro formas can make the package larger than the sum of the five reforms run alone.</p>";
    }
    if (chosen.cap_binding) {
      extra += "<p>Feasible capacity is " + integer(chosen.capacity_completions) +
        " completions. The five-year figure is the portion the absorption or adoption ceiling lets through.</p>";
    }
    drivers.className = "callout" + (chosen.cap_binding ? " warn" : "");
    drivers.innerHTML = "<strong>" + chosen.label + "</strong><ul>" + parts + "</ul>" + extra;
  }

  function renderMath() {
    var chosen = result.scenarios[scenarioId];
    mathFocus.textContent = chosen.label + " in " + result.name +
      ". The steps use " + result.focus_county + " as a worked example. The last step is the official state total, the sum of every county.";
    mathSteps.innerHTML = "";
    (chosen.trace || []).forEach(function (step, index) {
      var article = document.createElement("article");
      article.className = "step";
      article.innerHTML =
        "<h3>" + (index + 1) + ". " + escapeHtml(step.title) + "</h3>" +
        '<p class="eq">' + escapeHtml(step.equation) + "</p>" +
        '<p class="eq">' + escapeHtml(step.substitution) + "</p>" +
        '<p class="result">' + integer(step.result) + " " + escapeHtml(step.unit) + "</p>" +
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
      tr.innerHTML =
        "<td>" + escapeHtml(county.name) + (county.value_imputed ? " *" : "") + "</td>" +
        "<td>" + escapeHtml(county.context) + "</td>" +
        "<td>" + integer(county.baseline_completions) + "</td>" +
        "<td>" + integer(county.adu) + "</td>" +
        "<td>" + integer(county.missing_middle) + "</td>" +
        "<td>" + integer(county.tod) + "</td>" +
        "<td>" + integer(county.parking) + "</td>" +
        "<td>" + integer(county.fees) + "</td>" +
        "<td>" + integer(county.combined) + "</td>";
      countyBody.appendChild(tr);
    });
    var foot = document.createElement("tr");
    foot.innerHTML =
      "<td>Sum (equals rounded state total)</td><td></td>" +
      "<td>" + integer(totals.baseline_completions) + "</td>" +
      "<td>" + integer(totals.adu) + "</td>" +
      "<td>" + integer(totals.missing_middle) + "</td>" +
      "<td>" + integer(totals.tod) + "</td>" +
      "<td>" + integer(totals.parking) + "</td>" +
      "<td>" + integer(totals.fees) + "</td>" +
      "<td>" + integer(totals.combined) + "</td>";
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

  function render() {
    renderHeadline();
    renderCompare();
    renderMath();
    renderCounties();
    renderLimits();
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
    tornado.innerHTML = "";
    rows.forEach(function (row) {
      var line = document.createElement("div");
      line.className = "tornado-row";
      var lowLeft = Math.min(pos(row.low), pos(row.central));
      var highLeft = Math.min(pos(row.high), pos(row.central));
      line.innerHTML =
        "<span>" + escapeHtml(row.label) + "</span>" +
        '<div class="tornado-track" title="Low ' + integer(row.low) + " · central " + integer(row.central) + " · high " + integer(row.high) + '">' +
        '<i class="axis" style="left:' + pos(row.central) + '%"></i>' +
        '<i class="low" style="left:' + lowLeft + "%;width:" + Math.abs(pos(row.low) - pos(row.central)) + '%"></i>' +
        '<i class="high" style="left:' + highLeft + "%;width:" + Math.abs(pos(row.high) - pos(row.central)) + '%"></i>' +
        "</div>";
      tornado.appendChild(line);
    });
  }

  function renderBand(mc) {
    band.className = "callout";
    band.innerHTML = "<strong>Seeded band, " + mc.draws + " draws, seed " + mc.seed + ".</strong> " +
      "The 10th percentile is " + integer(mc.p10) +
      ", the median is " + integer(mc.p50) +
      ", and the 90th percentile is " + integer(mc.p90) +
      ". Draws are triangular on every published slider. The central case is " + integer(mc.p50 ? result.scenarios[scenarioId].incremental_completions : 0) +
      " only when the scenario is not the baseline; the band itself is the outcome the tornado uses.";
    var central = scenarioId === "baseline" ? result.baseline_completions_5yr : result.scenarios[scenarioId].incremental_completions;
    band.innerHTML = "<strong>Seeded band, " + mc.draws + " draws, seed " + mc.seed + ".</strong> " +
      "p10 " + integer(mc.p10) + " · p50 " + integer(mc.p50) + " · p90 " + integer(mc.p90) +
      ". The central point, with sliders at their published values, is " + integer(central) +
      ". Each draw samples every slider from a triangle on its low / central / high band.";
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
    if (payload.note) {
      var intro = document.createElement("p");
      intro.className = "help";
      intro.textContent = payload.note;
      crossOut.appendChild(intro);
    }
    Object.keys(payload.states || {}).forEach(function (code) {
      var item = payload.states[code];
      var card = document.createElement("article");
      card.className = "cross-card";
      var ratio = item.band_width_ratio == null ? "—" : Number(item.band_width_ratio).toFixed(2) + "×";
      var html = "<h3>" + code + " · tier " + item.tier + "</h3>" +
        "<p>Lot feasibility " + Math.round(item.lot_full * 100) + "% with the extract, " +
        Math.round(item.lot_imputed * 100) + "% when the extract is hidden. " +
        "Package band width " + integer(item.band_width_full) + " full versus " +
        integer(item.band_width_imputed) + " imputed (" + ratio + ").</p>" +
        "<table><thead><tr><th>Scenario</th><th>Full</th><th>Hidden parcels</th><th>Error</th><th>State median screen</th><th>Error</th></tr></thead><tbody>";
      Object.keys(names).forEach(function (id) {
        var block = item.scenarios[id];
        html += "<tr><td>" + names[id] + "</td><td>" + integer(block.imputed_parcels.full) +
          "</td><td>" + integer(block.imputed_parcels.other) +
          "</td><td>" + errorText(block.imputed_parcels) +
          "</td><td>" + integer(block.state_screen.other) +
          "</td><td>" + errorText(block.state_screen) + "</td></tr>";
      });
      html += "</tbody></table>";
      card.innerHTML = html;
      crossOut.appendChild(card);
    });
  }

  function errorText(block) {
    if (block.percent_error == null) return integer(block.gap) + " (small base)";
    return signedPercent(block.percent_error);
  }

  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function selectScenario(id) {
    scenarioId = id;
    if (result) {
      renderCompare();
      renderMath();
      renderLimits();
    }
    tornado.innerHTML = "";
    band.textContent = "Run the tornado to see which published assumptions move " + id.replace(/_/g, " ") + ".";
  }

  async function selectState(code) {
    stateCode = code;
    overrides = {};
    tornado.innerHTML = "";
    band.textContent = "";
    crossOut.innerHTML = "";
    document.querySelectorAll(".state-btn").forEach(function (button, index) {
      var pressed = button.querySelector("strong") && result ? false : false;
      button.classList.toggle("active", false);
      button.setAttribute("aria-pressed", "false");
      if (pressed) button.classList.add("active");
      void index;
    });
    setStatus("Loading " + code + "…");
    var spec = await request("/api/assumptions?state=" + encodeURIComponent(code));
    parameters = spec.parameters;
    renderSliders();
    await simulate();
    document.querySelectorAll("#state-list .state-btn").forEach(function (button) {
      var name = button.querySelector("strong").textContent;
      var active = result && name === result.name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  async function simulate() {
    var id = ++requestId;
    setStatus("Calculating " + stateCode + "…");
    var next = await post("/api/simulate", { state: stateCode, overrides: overrides });
    if (id !== requestId) return;
    result = next;
    setStatus("");
    render();
  }

  function fail(error) {
    setStatus(error && error.message ? error.message : "Something went wrong.");
  }

  document.querySelectorAll(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".tab").forEach(function (other) {
        other.classList.toggle("active", other === tab);
      });
      document.querySelectorAll(".panel").forEach(function (panel) {
        var on = panel.id === "panel-" + tab.getAttribute("data-tab");
        panel.hidden = !on;
        panel.classList.toggle("active", on);
      });
    });
  });

  document.getElementById("reset").addEventListener("click", function () {
    overrides = {};
    renderSliders();
    simulate().catch(fail);
  });

  document.getElementById("export-csv").addEventListener("click", function () { download("csv"); });
  document.getElementById("export-json").addEventListener("click", function () { download("json"); });
  document.getElementById("export-md").addEventListener("click", function () { download("md"); });

  document.getElementById("run-sensitivity").addEventListener("click", function () {
    setStatus("Running the tornado and the seeded band…");
    post("/api/sensitivity", { state: stateCode, scenario: scenarioId, draws: 80 })
      .then(function (payload) {
        renderTornado(payload.tornado);
        renderBand(payload.monte_carlo);
        setStatus("");
      })
      .catch(fail);
  });

  document.getElementById("run-cross").addEventListener("click", function () {
    setStatus("Cross-checking CT, WI, UT, and HI. This samples the published bands.");
    post("/api/crossval", { scope: "tier1", draws: 40 })
      .then(function (payload) {
        renderCross(payload);
        setStatus("");
      })
      .catch(fail);
  });

  async function download(fmt) {
    setStatus("Preparing the " + fmt.toUpperCase() + " export…");
    var response = await fetch("/api/export?state=" + encodeURIComponent(stateCode) + "&format=" + fmt);
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

  request("/api/states")
    .then(function (payload) {
      renderStates(payload.states);
      return selectState("PA");
    })
    .catch(fail);
})();
