/* Small Homes Policy Lab client. Locked results load first. One slider
   recomputes central, zoning, and ACS MOE; the envelope stays locked.
   Phase 2: build-your-package, count-up, Census shapes, tour, shareable views. */
(function () {
  "use strict";

  var ORDER = ["adu", "missing_middle", "parking", "fees", "package", "approval"];
  var BENCHMARKS = ["adu", "missing_middle", "parking", "fees"];
  var PLAIN = {
    missing_middle: "Allow 2–6 homes on single-family lots",
    fees: "Cut development fees",
    adu: "Allow backyard cottages (ADUs)",
    parking: "Reduce parking requirements",
    package: "All four together",
    approval: "By-right approval with a shot clock",
    baseline: "Baseline"
  };
  var ALIAS = { mm: "missing_middle", fees: "fees", adu: "adu", parking: "parking" };
  var SHORT = { missing_middle: "mm", fees: "fees", adu: "adu", parking: "parking" };
  var COL = { missing_middle: "#0e6e5c", fees: "#f2b632", adu: "#5b8fb9", parking: "#c8553d" };
  var CHIP_LABEL = { missing_middle: "2–6 homes", fees: "Fees", adu: "ADUs", parking: "Parking" };
  var HONESTY = "Added together, not modeled as a package";
  var HONESTY_LONG = "Added together, not modeled as a package. Overlap can push the real total down (ADUs and 2–6 homes compete for the same lots) or up (fee and parking cuts help both).";
  var TOUR_STEPS = [
    ["This is the answer", "The big number is extra homes over five years from the reforms you pick. The bar under it is the likely range, never hidden."],
    ["Flip a reform", "Each card is one bill. Turn it on or off and watch the total and the map change."],
    ["Don't add the bills up", "Reforms overlap. This panel shows the modeled total next to the separate cards when all four are on."],
    ["Take it with you", "Print a one-page brief with your package and its range, or copy a link to this view."]
  ];
  var WALK = [
    { title: "Pennsylvania is loaded", text: "All 67 counties and four Handbook scenarios are already computed. Unknown zoning is a prior, never zero." },
    { title: "Choose a Handbook reform", text: "Start with a Handbook reform. The cards show the increment versus Baseline." },
    { title: "Open Allegheny County", text: "Allegheny is the walkthrough. Pittsburgh's October 2026 ADU ordinance is observed; the rest of the county is unknown." },
    { title: "Why this result?", text: "Every input is tagged observed, assumed, or calculated. The ADU pro forma is illustrative." },
    { title: "Change one assumption", text: "Move the homeowner uptake hazard. Central, zoning, and ACS MOE recompute. The p10–p90 envelope does not." },
    { title: "Export a brief", text: "Download Markdown, HTML, or a county CSV. The brief states the ranking, including a tie when draw medians disagree with the central order, and what would change it." }
  ];
  var TIPS = {
    "pro forma": "A simple cost-and-value worksheet for one building type.",
    "uptake hazard": "The yearly chance a feasible lot actually starts a project.",
    prior: "A published guess used when a local rule has not been read.",
    Envelope: "The likely range from the locked test runs of the published assumptions.",
    "Likely range": "The 10th–90th percentile of the locked test runs. It describes the model, not the odds of success.",
    "Local-rules range": "How the answer moves if unknown local rules are more or less strict.",
    "Census survey error": "Census survey error on the counts and prices that feed the model.",
    Zoning: "How the answer moves if unknown local rules are more or less strict.",
    "ACS MOE": "Census survey error on the counts and prices that feed the model."
  };
  var RM = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var TOUR_KEY = "sf-lab-tour-v2";

  var stateCode = "PA";
  var scenarioId = "missing_middle";
  var unknownOn = [];
  var selectedFips = "42003";
  var on = new Set(["missing_middle"]);
  var mapId = "";
  var view = "map";
  var locked = null;
  var live = null;
  var geoDoc = null;
  var catalog = null;
  var whyDoc = null;
  var overrides = {};
  var appliedOverrides = {};
  var urlOverridesPending = false;
  var walkStep = 0;
  var whyOpen = false;
  var timer = null;
  var requestId = 0;
  var aduCompare = null;
  var aduCache = {};
  var shown = 0;
  var showAllCounties = false;
  var showAllDrivers = false;
  var tableSort = { key: "homes", dir: "desc" };
  var countyQuery = "";
  var animToken = 0;
  var lastFocus = null;
  var tourIndex = 0;
  var projBox = null;

  var statusEl = document.getElementById("status");
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
  var stateSelect = document.getElementById("state-select");

  function setStatus(text) { statusEl.textContent = text || ""; }

  function integer(value) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    return Math.round(n).toLocaleString("en-US");
  }

  var MIX_CSV_COLUMNS = [
    "fips", "county", "scenario", "central", "central_basis",
    "envelope_p10", "envelope_p90", "range_role",
    "zoning_low", "zoning_high", "acs_moe",
    "eligible_sum_of_reforms", "feasible_sum_of_reforms", "basis",
    "close_call_top_benchmark",
    "model", "seed", "fingerprint", "build_sha", "overrides"
  ];
  var SCENARIO_CSV_COLUMNS = [
    "fips", "county", "scenario", "central", "envelope_p10", "envelope_p90",
    "range_role", "zoning_low", "zoning_high", "acs_moe", "eligible", "feasible",
    "close_call_top_benchmark",
    "model", "seed", "fingerprint", "build_sha", "overrides"
  ];
  var CENTRAL_BASIS = "simple sum of standalone results, not modelled jointly";
  var COUNT_BASIS = "sum of per-reform counts; lots may overlap; not a joint count";

  function csvCell(value) {
    var text = value == null ? "" : String(value);
    if (/^[=+\-@\t\r]/.test(text) && !/^[+\-]?(\d+(\.\d*)?|\.\d+)([eE][+\-]?\d+)?$/.test(text)) {
      text = "'" + text;
    }
    if (/[",\r\n]/.test(text)) return '"' + text.replace(/"/g, '""') + '"';
    return text;
  }

  function csvLine(fields) {
    return fields.map(csvCell).join(",");
  }

  function oneDecimal(value) {
    var n = Number(value);
    if (!isFinite(n)) return "";
    return (Math.round(n * 10) / 10).toFixed(1);
  }

  function csvMeta(opts) {
    return [
      opts.model || "county",
      opts.seed == null ? "" : String(opts.seed),
      opts.fingerprint || "",
      opts.sha || "",
      opts.overrides || ""
    ];
  }

  function customSelection(ids) {
    return !ids || (ids.length !== 1 && ids.length !== 4);
  }

  function buildCountyCsv(counties, ids, opts) {
    opts = opts || {};
    var lockedCounties = opts.lockedCounties || counties || [];
    var custom = customSelection(ids);
    var header = custom ? MIX_CSV_COLUMNS : SCENARIO_CSV_COLUMNS;
    var lines = [csvLine(header)];
    var role = opts.live ? "reference_at_default_settings" : "conditional_on_published_assumptions";
    (counties || []).forEach(function (row) {
      if (custom) {
        var central = 0;
        var eligible = 0;
        var feasible = 0;
        (ids || []).forEach(function (id) {
          var part = row.results && row.results[id];
          if (!part) return;
          central += Number(part.central) || 0;
          eligible += Number(part.eligible) || 0;
          feasible += Number(part.feasible) || 0;
        });
        var empty = !ids || !ids.length;
        lines.push(csvLine([
          row.fips,
          row.name,
          empty ? "none" : "selection",
          empty ? "0.0" : oneDecimal(central),
          empty ? "no reforms selected" : CENTRAL_BASIS,
          "",
          "",
          "Reference range (defaults) not computed for this mix",
          "",
          "",
          "",
          empty ? "" : oneDecimal(eligible),
          empty ? "" : oneDecimal(feasible),
          empty ? "" : COUNT_BASIS,
          "not computed for mix"
        ].concat(csvMeta(opts))));
        return;
      }
      var sid = ids.length === 4 ? "package" : ids[0];
      var current = (row.results && row.results[sid]) || {};
      var lockedRow = lockedCounties.filter(function (item) { return item.fips === row.fips; })[0] || row;
      var env = (lockedRow.results && lockedRow.results[sid]) || current;
      var close = false;
      if (lockedRow.top_benchmark_pair) close = !!lockedRow.top_benchmark_pair.close_call;
      else if (lockedRow.pairs) {
        close = Object.keys(lockedRow.pairs).some(function (key) { return lockedRow.pairs[key][1]; });
      }
      lines.push(csvLine([
        row.fips,
        row.name,
        sid,
        oneDecimal(current.central),
        isFinite(Number(env.p10)) ? oneDecimal(env.p10) : "",
        isFinite(Number(env.p90)) ? oneDecimal(env.p90) : "",
        role,
        oneDecimal(current.zoning_low),
        oneDecimal(current.zoning_high),
        oneDecimal(current.acs_moe),
        oneDecimal(current.eligible || 0),
        oneDecimal(current.feasible || 0),
        close ? "yes" : "no"
      ].concat(csvMeta(opts))));
    });
    return lines.join("\n") + "\n";
  }

  function describeRange(row) {
    if (!row || row.interval_status === "unavailable" || !isFinite(Number(row.p10)) || !isFinite(Number(row.p90))) {
      return "Likely range unavailable";
    }
    var text = integer(row.p10) + "–" + integer(row.p90);
    if (row.interval_status === "reference") return "Reference range (defaults) " + text;
    return "Likely range " + text;
  }

  function encodeOverrides(map) {
    return Object.keys(map).sort().map(function (name) {
      return name + ":" + map[name];
    }).join(",");
  }

  function decodeOverrides(raw, allowed) {
    var out = {};
    if (!raw) return out;
    raw.split(",").forEach(function (part) {
      var idx = part.lastIndexOf(":");
      if (idx <= 0) return;
      var name = part.slice(0, idx);
      var value = Number(part.slice(idx + 1));
      if (!name || !isFinite(value)) return;
      if (allowed && !allowed[name]) return;
      out[name] = value;
    });
    return out;
  }

  function allowedOverrides() {
    var allowed = {};
    if (!catalog || !catalog.parameters) return null;
    catalog.parameters.forEach(function (row) { allowed[row.name] = true; });
    return allowed;
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

  var TIP_TEXT = {
    observed: "Measured in a public dataset and stored for this place.",
    assumed: "A published assumption or an imputation. It is not a measurement for this place.",
    calculated: "Arithmetic in the model, using observed inputs and published assumptions."
  };
  var tipSerial = 0;

  function tipControl(label, tip, className) {
    if (!tip) return escapeHtml(label);
    var id = window.StateframeFmt && window.StateframeFmt.nextTipId
      ? window.StateframeFmt.nextTipId()
      : "tip-lab-" + (++tipSerial);
    return '<button type="button" class="tip' + (className ? " " + className : "") + '" aria-describedby="' + id +
      '" aria-expanded="false">' + escapeHtml(label) + '</button><span class="tip-pop" id="' + id +
      '" role="tooltip" hidden>' + escapeHtml(tip) + "</span>";
  }

  function closeTips() {
    document.querySelectorAll("button.tip[aria-expanded='true']").forEach(function (btn) {
      btn.setAttribute("aria-expanded", "false");
      var pop = document.getElementById(btn.getAttribute("aria-describedby"));
      if (pop) pop.hidden = true;
    });
  }

  function jargon(term, text) {
    return tipControl(text || term, TIPS[term] || "");
  }

  function tag(kind) {
    return tipControl(kind, TIP_TEXT[kind] || kind, "tag " + kind);
  }

  function scenarioLabel(sid) {
    if (PLAIN[sid]) return PLAIN[sid];
    var row = (locked && locked.scenarios || []).filter(function (s) { return s.id === sid; })[0];
    var raw = row ? row.short : sid;
    return String(raw).replace(/^\d+\.\s*/, "");
  }

  function cardTitle(row) {
    return PLAIN[row.id] || String(row.label || row.short || row.id).replace(/^\d+\.\s*/, "");
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

  function selectedIds() {
    return rankedBenchmarks().filter(function (k) { return on.has(k); });
  }

  function rankedBenchmarks() {
    var rank = (locked && locked.statewide && locked.statewide.benchmark_ranking) || BENCHMARKS;
    return rank.filter(function (id) { return BENCHMARKS.indexOf(id) >= 0; });
  }

  function activeScenario() {
    var ids = selectedIds();
    if (!ids.length) return "";
    if (ids.length === 1) return ids[0];
    if (ids.length === 4) return "package";
    return "selection";
  }

  function selectionLabel() {
    return selectedIds().map(scenarioLabel).join(" and ");
  }

  function bandOf(row) {
    if (!row || !isFinite(Number(row.p10)) || !isFinite(Number(row.p90))) {
      return { lo: null, hi: null, status: (row && row.interval_status) || "unavailable" };
    }
    return { lo: Number(row.p10), hi: Number(row.p90), status: row.interval_status || "conditional" };
  }

  function packageTotal() {
    var ids = selectedIds();
    var sw = docStatewide().results;
    if (!ids.length) return { c: 0, lo: 0, hi: 0, exact: true, status: "conditional" };
    if (ids.length === 1) {
      var one = sw[ids[0]];
      var band = bandOf(one);
      return { c: one.central, lo: band.lo, hi: band.hi, exact: true, status: band.status };
    }
    if (ids.length === 4) {
      var pack = sw.package;
      var packed = bandOf(pack);
      return { c: pack.central, lo: packed.lo, hi: packed.hi, exact: true, status: packed.status };
    }
    var sum = ids.reduce(function (a, k) { return a + Number(sw[k].central); }, 0);
    return { c: sum, lo: null, hi: null, exact: false, status: "unmodeled" };
  }

  function countyPackageValue(row) {
    var ids = selectedIds();
    if (!ids.length) return 0;
    if (ids.length === 4) return cell(row, "package").central;
    return ids.reduce(function (a, k) { return a + Number(cell(row, k).central); }, 0);
  }

  function mapScenarioId() {
    var ids = selectedIds();
    if (!ids.length) return "";
    if (ids.length === 1) return ids[0];
    if (ids.length === 4) return "package";
    return "selection";
  }

  function countyMapValue(row) {
    var sid = mapScenarioId();
    if (!sid) return 0;
    if (sid === "package") return cell(row, "package").central;
    if (sid === "selection") return countyPackageValue(row);
    if (BENCHMARKS.indexOf(sid) >= 0) return Number(cell(row, sid).central);
    return 0;
  }

  function stateNameOf(code) {
    return code === "NH" ? "New Hampshire" : "Pennsylvania";
  }

  function countyPhrase(row) {
    var name = (row && row.name) || "";
    if (!/ County$/i.test(name)) name = name + " County";
    return "In " + name + ":";
  }

  function fetchWithTimeout(url, options) {
    var controller = typeof AbortController === "function" ? new AbortController() : null;
    var timer = setTimeout(function () {
      if (controller) controller.abort();
    }, 20000);
    var opts = Object.assign({}, options || {});
    if (controller) opts.signal = controller.signal;
    return fetch(url, opts).finally(function () { clearTimeout(timer); });
  }

  function get(path) {
    return fetchWithTimeout(path).then(function (res) {
      if (!res.ok) return res.json().then(function (body) { throw new Error(body.error || res.statusText); });
      return res.json();
    });
  }

  function post(path, payload) {
    return fetchWithTimeout(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (!res.ok) return res.json().then(function (body) { throw new Error(body.error || res.statusText); });
      return res.json();
    });
  }

  var unknownState = "";

  function renderStateNotice() {
    var el = document.getElementById("state-notice");
    if (!el) return;
    if (!unknownState) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = "Unknown state " + unknownState + ", showing PA.";
  }

  function parseUrl() {
    var q = new URLSearchParams(location.search);
    var st = (q.get("st") || "").toUpperCase();
    if (st && st !== "PA" && st !== "NH") {
      unknownState = st;
      stateCode = "PA";
    } else if (st === "PA" || st === "NH") {
      unknownState = "";
      stateCode = st;
    }
    unknownOn = [];
    if (q.has("on")) {
      var raw = q.get("on") || "";
      on = new Set();
      if (raw && raw !== "none") {
        raw.split(",").forEach(function (part) {
          if (!part) return;
          var id = ALIAS[part] || part;
          if (BENCHMARKS.indexOf(id) >= 0) on.add(id);
          else unknownOn.push(id);
        });
        if (!on.size && !unknownOn.length) on.add("missing_middle");
      }
    }
    if (q.has("ov")) {
      overrides = decodeOverrides(q.get("ov") || "");
      urlOverridesPending = true;
    }
    var mapped = q.get("map");
    if (mapped) {
      if (mapped === "all" || mapped === "package") mapId = "package";
      else {
        var mid = ALIAS[mapped] || mapped;
        mapId = BENCHMARKS.indexOf(mid) >= 0 ? mid : "";
      }
    }
    var county = q.get("county");
    if (county) selectedFips = county;
    var v = q.get("view");
    if (v === "map" || v === "table" || v === "chart") view = v;
    if (on.size === 1) scenarioId = selectedIds()[0];
    else if (on.size === 4) scenarioId = "package";
  }

  function writeUrl() {
    var q = new URLSearchParams();
    q.set("st", stateCode);
    var chosen = selectedIds();
    q.set("on", chosen.length ? chosen.map(function (id) { return SHORT[id]; }).join(",") : "none");
    var ov = encodeOverrides(overrides);
    if (ov) q.set("ov", ov);
    if (mapId) q.set("map", mapId === "package" ? "package" : (SHORT[mapId] || mapId));
    if (selectedFips) q.set("county", selectedFips);
    q.set("view", view);
    history.replaceState(null, "", "?" + q.toString() + location.hash);
    renderStateNotice();
  }

  function loadAduCompare(code) {
    if (aduCache[code]) return Promise.resolve(aduCache[code]);
    return get("/api/adu-compare?state=" + code).then(function (doc) {
      aduCache[code] = doc;
      return doc;
    });
  }

  function fillAduFeeNote() {
    var el = document.getElementById("adu-fee-note");
    if (!el || !aduCompare || !aduCompare.notes) return;
    el.innerHTML = aduCompare.notes.lab_html || "";
  }

  function renderTryPa() {
    var btn = document.getElementById("try-pa");
    if (!btn) return;
    var showing = stateCode === "PA";
    btn.hidden = showing;
    if (showing) btn.setAttribute("aria-hidden", "true");
    else btn.removeAttribute("aria-hidden");
  }

  function showRetry(retry) {
    if (!statusEl) return;
    statusEl.textContent = "";
    statusEl.appendChild(document.createTextNode("Couldn't load this view. "));
    var button = document.createElement("button");
    button.type = "button";
    button.textContent = "Retry";
    button.addEventListener("click", retry || function () { loadAll(); });
    statusEl.appendChild(button);
  }

  function loadAll() {
    var id = ++requestId;
    var nameEl = document.getElementById("state-name");
    if (nameEl) nameEl.textContent = stateNameOf(stateCode);
    if (stateSelect) stateSelect.value = stateCode;
    if (locked && locked.state !== stateCode) {
      live = null;
      shown = 0;
      animToken += 1;
      if (headline) headline.innerHTML = "";
      var countEl = document.getElementById("count");
      if (countEl) countEl.textContent = "…";
      var rangeEl = document.getElementById("rangeline");
      if (rangeEl) rangeEl.textContent = "";
      var relateEl = document.getElementById("relate");
      if (relateEl) relateEl.textContent = "";
      if (countyDetail) { countyDetail.hidden = true; countyDetail.textContent = ""; }
      var mini = document.getElementById("mini-total");
      if (mini) { mini.hidden = true; mini.textContent = ""; }
    }
    setStatus("Loading " + (stateCode === "PA" ? "Pennsylvania's 67 counties" : "New Hampshire's 10 counties") + "…");
    return Promise.all([
      get("/api/lab/results?state=" + stateCode),
      get("/api/lab/geo?state=" + stateCode),
      catalog ? Promise.resolve(catalog) : get("/api/lab/assumptions"),
      loadAduCompare(stateCode)
    ]).then(function (parts) {
      if (id !== requestId) return;
      locked = parts[0];
      geoDoc = parts[1];
      catalog = parts[2];
      aduCompare = parts[3];
      live = null;
      var keepOverrides = urlOverridesPending;
      urlOverridesPending = false;
      if (!keepOverrides) overrides = {};
      else overrides = decodeOverrides(encodeOverrides(overrides), allowedOverrides());
      appliedOverrides = {};
      if (stateCode === "PA") selectedFips = selectedFips || "42003";
      else if (!countyRow(selectedFips)) selectedFips = locked.counties[0].fips;
      if (stateSelect) stateSelect.value = stateCode;
      fillAduFeeNote();
      renderTryPa();
      renderAll();
      if (keepOverrides && Object.keys(overrides).length) scheduleRecompute();
      if (whyOpen) loadWhy();
      setStatus("");
    }).catch(function () {
      showRetry(function () { loadAll(); });
    });
  }

  function renderAll() {
    renderStateNotice();
    if (!locked || locked.state !== stateCode) return;
    renderHeadline();
    renderCount();
    renderCards();
    renderOverlap();
    renderChips();
    renderMap();
    renderTable();
    renderChart();
    renderCountySelect();
    renderSliders();
    renderWalk();
    renderKeyPoints();
    renderSources();
    renderBrief();
    renderDrivers();
    renderModelDiff();
    renderRecon();
    setView(view, true);
    writeUrl();
  }

  function changeState(code) {
    unknownState = "";
    stateCode = code;
    selectedFips = code === "PA" ? "42003" : null;
    walkStep = 0;
    shown = 0;
    animToken += 1;
    loadAll();
  }

  function medianShort(id) {
    return ({ adu: "ADU", missing_middle: "MM", fees: "Fees", parking: "Parking" })[id] || scenarioLabel(id);
  }

  function isDrawTie(pair) {
    return !!(pair && pair.close_call && pair.flip_share >= 0.5);
  }

  function topPairTieClause(sw) {
    var pair = sw.top_benchmark_pair;
    var trail = sw.results[pair.trailer];
    var lead = sw.results[pair.leader];
    return "Central estimate favors " + scenarioLabel(pair.leader) +
      "; " + scenarioLabel(pair.trailer) + " ahead in " + Math.round(pair.flip_share * 100) +
      "% of draws (draw medians " + medianShort(pair.trailer) + " " + integer(trail.p50) +
      " vs " + medianShort(pair.leader) + " " + integer(lead.p50) + ")";
  }

  function mixUnranked() {
    var n = on.size;
    return n !== 1 && n !== 4;
  }

  function rankingLine(sw) {
    var rank = sw.benchmark_ranking || [];
    if (isDrawTie(sw.top_benchmark_pair) && rank.length >= 2) {
      return "Too close to call (" + scenarioLabel(rank[0]) + " and " + scenarioLabel(rank[1]) + ")" +
        (rank.length > 2 ? " > " + rank.slice(2).map(scenarioLabel).join(" > ") : "");
    }
    return rank.map(scenarioLabel).join(" > ");
  }

  function rankingBadge(pair, sw, flipPath) {
    var threshold = (locked && locked.close_call_flip_share_label) || "close-call threshold";
    if (!pair || !pair.close_call) {
      return '<span class="badge-holds">Ranking holds</span>';
    }
    var path = flipPath || "statewide.top_benchmark_pair.flip_share";
    var county = path.indexOf("counties.") === 0 ? path.split(".")[1] : "";
    function resultPath(sid, field) {
      return county
        ? "counties." + county + ".results." + sid + "." + field
        : "statewide.results." + sid + "." + field;
    }
    var flip = bound(path, Math.round(pair.flip_share * 100) + "%");
    var gate = bound("close_call_flip_share", Math.round((locked && locked.close_call_flip_share ? locked.close_call_flip_share : 0.1) * 100) + "%");
    if (isDrawTie(pair) && sw) {
      var trail = sw.results[pair.trailer];
      var lead = sw.results[pair.leader];
      return tipControl("Too close to call", "The order flips often enough to call the ranking a tie. " + threshold + ".") +
        '<span class="sr">Central estimate favors ' + escapeHtml(scenarioLabel(pair.leader)) +
        "; " + escapeHtml(scenarioLabel(pair.trailer)) + " comes out ahead in " + flip +
        " of test runs (typical result " +
        bound(resultPath(pair.trailer, "p50"), integer(trail.p50)) + " vs " +
        bound(resultPath(pair.leader, "p50"), integer(lead.p50)) +
        "). The threshold is " + gate + ".</span>";
    }
    var keep = pair.flip_share != null ? Math.round((1 - pair.flip_share) * 5) : 4;
    if (keep >= 5) return '<span class="badge-holds">Ranking holds</span>';
    if (keep < 1) keep = 1;
    var kept = '<span data-derived="kept-runs" data-from="' + escapeHtml(path) + '">' + keep + "</span>";
    return tipControl("Too close to call", "The order flips often enough that a different published assumption can swap the top two. " + threshold + ".") +
      '<span class="sr">' + escapeHtml(scenarioLabel(pair.leader)) + " beat " +
      escapeHtml(scenarioLabel(pair.trailer)) + " in about " + kept + " of 5 test runs (" +
      flip + "). The threshold is " + gate + ".</span>";
  }

  function frameApi() {
    return window.StateframeFrame || null;
  }

  function drawsNote() {
    var n = locked && locked.draws ? Number(locked.draws).toLocaleString("en-US") : "";
    return "Move one slider. The middle estimate, the local-rules range, and the Census survey error update. The likely range stays on the locked" +
      (n ? " " + n + "-draw" : "") + " run.";
  }

  function endYearText() {
    if (!catalog || !catalog.window_start) return "";
    var start = Number(String(catalog.window_start).slice(0, 4));
    if (!isFinite(start)) return "";
    return String(start + Number(catalog.horizon_years) - 1);
  }

  function headlineSid() {
    var ids = selectedIds();
    if (ids.length === 1) return ids[0];
    if (ids.length === 4) return "package";
    return "";
  }

  function headlineOpts() {
    var sid = headlineSid();
    var unmodeled = on.size > 1 && !sid;
    var sw = docStatewide();
    var row = sid ? sw.results[sid] : null;
    var t = packageTotal();
    var base = sw.results.baseline;
    return {
      sid: unmodeled ? "" : sid,
      unmodeled: unmodeled,
      status: row ? (row.interval_status || t.status) : t.status,
      stateName: locked.name,
      endYear: endYearText(),
      label: sid ? scenarioLabel(sid) : "Your package",
      low: row ? row.p10 : null,
      high: row ? row.p90 : null,
      middle: row ? row.central : null,
      baseline: base.central,
      draws: locked.draws,
      paths: sid ? {
        low: "statewide.results." + sid + ".p10",
        high: "statewide.results." + sid + ".p90",
        middle: "statewide.results." + sid + ".central",
        baseline: "statewide.results.baseline.central",
        endYear: "assumptions.end_year",
        draws: "draws"
      } : {}
    };
  }

  function answerLine() {
    var t = packageTotal();
    var sw = docStatewide();
    var baseline = sw.results.baseline.central;
    if (!on.size) return "Pick a reform to see the extra homes.";
    if (t.exact && t.status !== "unavailable" && isFinite(Number(t.lo)) && isFinite(Number(t.hi))) {
      var rangeWord = t.status === "reference"
        ? "Reference range — from default assumptions, not recomputed "
        : "Likely ";
      return rangeWord + integer(t.lo) + "–" + integer(t.hi) +
        " extra homes. Middle estimate " + signed(t.c) +
        ". On top of " + integer(baseline) + " expected without these reforms.";
    }
    if (t.exact && t.status === "unavailable") {
      return "Likely range unavailable. Middle estimate " + signed(t.c) +
        " extra homes, on top of " + integer(baseline) + " expected.";
    }
    return "Likely range unavailable. Middle estimate " + signed(t.c) +
      " extra homes (" + HONESTY + ") on top of " + integer(baseline) + " expected.";
  }

  function renderHeadline() {
    var sw = docStatewide();
    var api = frameApi();
    var opts = headlineOpts();
    document.getElementById("state-name").textContent = locked.name;
    var years = endYearText();
    document.getElementById("kicker").textContent = years
      ? "Your package · " + String(catalog.window_start).slice(0, 4) + "–" + years
      : "Your package";
    var parts = api ? api.headlineParts(opts) : { html: "<p>" + escapeHtml(answerLine()) + "</p>", rangeHtml: "", middleHtml: "", live: answerLine() };
    if (headline) headline.innerHTML = parts.html +
      (opts.unmodeled ? "" : '<p class="hero-rank">' + (mixUnranked()
        ? ""
        : rankingBadge(sw.top_benchmark_pair, sw)) + "</p>") +
      (locked.state === "NH"
        ? '<p class="hero-meta">New Hampshire already allows ADUs statewide, so the ADU reform adds ' +
          signed(sw.results.adu.central) + ". Same code, same assumptions, a second state.</p>"
        : "");
    var countEl = document.getElementById("count");
    if (countEl) countEl.innerHTML = parts.rangeHtml || "";
    var mid = document.getElementById("middle-est");
    if (mid) mid.innerHTML = parts.middleHtml || "";
    var liveEl = document.getElementById("count-live");
    if (liveEl) liveEl.textContent = parts && Object.prototype.hasOwnProperty.call(parts, "live") ? parts.live : answerLine();
  }

  function anim(to) {
    var token = ++animToken;
    var from = shown;
    var t0 = performance.now();
    var dur = RM ? 0 : 900;
    function step(t) {
      if (token !== animToken) return;
      var p = dur ? Math.min(1, (t - t0) / dur) : 1;
      var e = 1 - Math.pow(1 - p, 3);
      shown = from + (to - from) * e;
      document.getElementById("count").textContent = "+" + integer(Math.max(0, shown));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function renderCount() {
    var t = packageTotal();
    var sw = docStatewide();
    var baseline = sw.results.baseline.central;
    var mx = Math.max(sw.results.package.p90 * 1.05, 1);
    var band = document.getElementById("band");
    var tick = document.getElementById("tick");
    if (band) {
      band.classList.toggle("reference", t.status === "reference");
      if (t.exact && isFinite(Number(t.lo)) && isFinite(Number(t.hi))) {
        band.style.left = (Math.max(0, t.lo) / mx * 100) + "%";
        band.style.width = (Math.max(0, t.hi - t.lo) / mx * 100) + "%";
      } else {
        band.style.left = "0";
        band.style.width = "0";
      }
    }
    if (tick) tick.style.left = (Math.max(0, t.c) / mx * 100) + "%";
    var range = document.getElementById("rangeline");
    if (range) {
      if (!on.size) range.textContent = "";
      else if (!t.exact) range.textContent = "";
      else range.innerHTML = "Range from " + bound("draws", integer(locked.draws)) + " runs of the published assumptions; it describes the model, not the odds of success.";
    }
    var relate = document.getElementById("relate");
    if (relate) {
      if (!on.size || !baseline || !t.exact) relate.textContent = "";
      else {
        var share = (t.c / baseline * 100).toFixed(1) + "%";
        var sid = headlineSid();
        relate.innerHTML = "That's about " +
          bound("derived.lift." + (sid || "package"), share) + " more homes than " +
          bound("statewide.results.baseline.central", integer(baseline)) +
          " expected anyway over five years.";
      }
    }
    var mini = document.getElementById("mini-total");
    var api = frameApi();
    if (mini) {
      mini.hidden = !on.size;
      if (!on.size) mini.textContent = "";
      else if (api) mini.innerHTML = api.miniTotal(headlineOpts());
      else mini.textContent = answerLine();
    }
  }

  function renderRecon() {
    var yaml = catalog && catalog.reconciliation_note;
    var note = aduCompare && aduCompare.notes && aduCompare.notes.engine_gap_lab_html;
    var box = document.getElementById("recon");
    var methods = document.getElementById("methods-recon");
    var html = yaml || note || "";
    if (!html) return;
    if (box) {
      box.hidden = false;
      if (yaml) box.textContent = yaml;
      else box.innerHTML = note;
    }
    if (methods) {
      methods.hidden = false;
      if (yaml) methods.textContent = yaml;
      else methods.innerHTML = note;
    }
  }

  function placeLabel(index, key, sw) {
    var pair = sw.top_benchmark_pair;
    if (!mixUnranked() && isDrawTie(pair) && (key === pair.leader || key === pair.trailer)) return "Too close to call";
    return "#" + (index + 1) + " on its own";
  }

  function closeBadgeHtml(k, sw) {
    var pair = sw.top_benchmark_pair;
    if (mixUnranked()) return "";
    if (!pair || !pair.close_call) return "";
    if (k !== pair.leader && k !== pair.trailer) return "";
    var flip = bound("statewide.top_benchmark_pair.flip_share", Math.round(pair.flip_share * 100) + "%");
    if (isDrawTie(pair)) {
      return '<button type="button" class="badge" aria-expanded="false" data-badge="close">Too close to call</button>' +
        '<span class="sr">' + escapeHtml(scenarioLabel(pair.trailer)) + " ahead in " + flip +
        " of test runs. The central estimate favors " + escapeHtml(scenarioLabel(pair.leader)) + ".</span>";
    }
    return '<button type="button" class="badge" aria-expanded="false" data-badge="close">Too close to call</button>' +
      '<span class="sr">' + escapeHtml(scenarioLabel(pair.trailer)) + " ahead in " + flip +
      " of test runs. Both are strong options.</span>";
  }

  function outcomeBadgeHtml(row) {
    if (!row || row.interval_status === "reference" || row.interval_status === "unavailable") return "";
    if (!isFinite(Number(row.p10)) || row.p10 > 0) return "";
    return '<button type="button" class="badge badge-out" aria-expanded="false" data-badge="out">Outcome uncertain</button>';
  }

  function bound(path, text) {
    return '<span data-bind="' + escapeHtml(path) + '">' + text + "</span>";
  }

  function paramSpec(name) {
    var spec = null;
    ((catalog && catalog.parameters) || []).forEach(function (row) {
      if (row.name === name) spec = row;
    });
    if (!spec && catalog && catalog.anchors && catalog.anchors[name]) spec = catalog.anchors[name];
    return spec;
  }

  function paramText(name) {
    var spec = paramSpec(name);
    if (!spec) return "";
    var value = Object.prototype.hasOwnProperty.call(overrides, name) ? overrides[name] : spec.central;
    if (spec.unit === "spaces per home") {
      var n = Math.round(Number(value) * 100) / 100;
      return String(n);
    }
    return sliderValueText(spec, value);
  }

  function cardExtras(k, row) {
    var api = frameApi();
    if (!api || !row) return "";
    var prefix = "statewide.results." + k;
    var drivers = api.rankDrivers(locked.statewide.one_at_a_time, k, catalog ? catalog.parameters : []);
    var funnel = api.funnelHtml({
      sid: k,
      funnel: row.funnel,
      stateName: locked.name,
      label: scenarioLabel(k),
      endYear: endYearText(),
      prefix: prefix + ".funnel",
      middle: row.central,
      middlePath: prefix + ".central",
      low: row.p10,
      high: row.p90,
      lowPath: prefix + ".p10",
      highPath: prefix + ".p90",
      feesLotHomes: row.host_delta,
      feesPath: prefix + ".host_delta",
      collapseSteps: true
    });
    var parking = k === "parking" ? api.parkingHtml({
      show: true,
      urbanText: paramText("parking_market_urban"),
      urbanPath: "by_name.parking_market_urban.central",
      minText: paramText("parking_min_urban"),
      minPath: "anchors.parking_min_urban.central"
    }) : "";
    var limits = api.limitsHtml({
      sid: k,
      drivers: drivers,
      driverSid: k,
      ratios: catalog && catalog.completion_ratios,
      low: row.p10,
      high: row.p90,
      baseline: docStatewide().results.baseline.central,
      lowPath: prefix + ".p10",
      highPath: prefix + ".p90",
      parkingText: paramText("parking_market_urban"),
      parkingPath: "by_name.parking_market_urban.central"
    });
    return funnel + parking + limits + '<p class="model-badge county">County model</p>';
  }

  function renderCards() {
    var sw = docStatewide();
    var rank = rankedBenchmarks();
    var mx = Math.max(sw.results.package.p90, 1);
    var api = frameApi();
    cards.innerHTML = rank.map(function (k, i) {
      var row = sw.results[k];
      var pressed = on.has(k);
      var prefix = "statewide.results." + k;
      var rangeHtml = api
        ? ((row.interval_status === "reference"
            ? "Reference range — from default assumptions, not recomputed "
            : "Likely ") + api.rangeSpans(prefix + ".p10", prefix + ".p90", row.p10, row.p90) + " extra homes")
        : describeRange(row);
      return '<div class="card" role="listitem">' +
        '<button type="button" class="tog" aria-pressed="' + pressed + '" data-k="' + k + '">' +
        "<span><span class='help'>" + escapeHtml(placeLabel(i, k, sw)) + "</span><span class='card-title'>" +
        escapeHtml(PLAIN[k]) + "</span></span><span class='sw' aria-hidden='true'></span></button>" +
        '<p class="card-range">' + rangeHtml + "</p>" +
        '<div class="n">Middle estimate ' + bound(prefix + ".central", signed(row.central)) + tag("calculated") + "</div>" +
        '<div class="mini" aria-hidden="true"><i style="left:' + (Math.max(0, row.p10) / mx * 100) +
        "%;width:" + (Math.max(0, row.p90 - row.p10) / mx * 100) + '%"></i><b style="left:' +
        (Math.max(0, row.central) / mx * 100) + '%"></b></div>' +
        '<div class="r">' + (row.interval_status === "reference"
          ? "Reference range (defaults)" : "Likely range (10th–90th percentile, model-conditional)") + "</div>" +
        closeBadgeHtml(k, sw) + outcomeBadgeHtml(row) + cardExtras(k, row) + "</div>";
    }).join("");
    extraCards.innerHTML = (locked.scenarios || []).filter(function (s) {
      return s.id === "approval";
    }).map(function (s) {
      var row = sw.results[s.id];
      return '<article class="scenario-card" data-sid="' + s.id + '"><div class="card-top"><h3><button type="button" data-sid="' +
        s.id + '">' + escapeHtml(cardTitle(s)) + "</button></h3><span class='pill t2'>extra</span></div>" +
        "<p class='plain'>" + bound("statewide.results.approval.central", signed(row.central)) + " vs Baseline" + tag("calculated") +
        ". Not part of the package.</p></article>";
    }).join("");
    cards.querySelectorAll(".tog").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var k = btn.getAttribute("data-k");
        if (on.has(k)) on.delete(k);
        else on.add(k);
        scenarioId = k;
        if (walkStep === 1) walkStep = 2;
        renderAll();
        if (whyOpen) loadWhy();
      });
    });
    cards.querySelectorAll("[data-badge]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var open = btn.getAttribute("aria-expanded") === "true";
        btn.setAttribute("aria-expanded", open ? "false" : "true");
        if (btn.getAttribute("data-badge") === "close") {
          var pair = docStatewide().top_benchmark_pair;
          var ahead = scenarioLabel(pair.trailer) + " ahead in " + Math.round(pair.flip_share * 100) + "% of test runs.";
          if (isDrawTie(pair)) {
            btn.textContent = open ? "Too close to call" :
              "Too close to call: central estimate favors " + scenarioLabel(pair.leader) + "; " + ahead;
          } else {
            btn.textContent = open ? "Too close to call" : "Too close to call: " + ahead + " Both are strong options.";
          }
        } else {
          btn.textContent = open ? "Outcome uncertain" : "Outcome uncertain: under some assumptions this reform adds no homes.";
        }
      });
    });
    extraCards.querySelectorAll("[data-sid]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        scenarioId = btn.getAttribute("data-sid");
        renderAll();
        if (whyOpen) loadWhy();
      });
    });
  }

  function renderOverlap() {
    var ids = selectedIds();
    var sw = docStatewide();
    var t = packageTotal();
    var sum = ids.reduce(function (a, k) { return a + Number(sw.results[k].central); }, 0);
    var width = Math.max(sum, t.c, 1) * 1.05;
    document.getElementById("stack").innerHTML = ids.map(function (k) {
      return '<span style="width:' + (sw.results[k].central / width * 100) + "%;background:" +
        COL[k] + '" role="img" aria-label="' + escapeHtml(PLAIN[k]) + '"></span>';
    }).join("");
    var line = document.getElementById("sumline");
    var box = document.getElementById("overlap");
    if (ids.length < 2) {
      line.textContent = "Turn on two or more reforms to see how they interact.";
      box.textContent = "";
      return;
    }
    if (ids.length === 4) {
      var d = sw.package_decomposition || locked.statewide.package_decomposition;
      var root = "statewide.package_decomposition.";
      line.innerHTML = "Adding the cards: <b>" + bound(root + "sum_of_separate", integer(d.sum_of_separate)) +
        "</b>. Modeled together: <b>" + bound(root + "package", integer(d.package)) + "</b>." + tag("calculated");
      box.innerHTML = "<b>Don't add the bills up.</b> ADUs and 2–6 homes compete for the same lots (" +
        bound(root + "competition_loss", integer(Math.abs(d.competition_loss))) +
        " fewer homes than adding them), but a fee cut is worth more when paired with them (fee step " +
        bound(root + "fee_cut_step", signed(d.fee_cut_step)) + ", parking step " +
        bound(root + "parking_step", signed(d.parking_step)) + "). Net: " +
        bound(root + "package", integer(d.package)) + " vs " +
        bound(root + "sum_of_separate", integer(d.sum_of_separate)) + " if added. Interaction " +
        bound(root + "interaction", signed(d.interaction)) + ". Package is not a sum." + tag("calculated");
    } else {
      var parts = ids.map(function (k) {
        return escapeHtml(PLAIN[k]) + " " + bound("statewide.results." + k + ".central", signed(sw.results[k].central));
      }).join(", ");
      line.innerHTML = "Adding the cards: " + parts + ". " + escapeHtml(HONESTY);
      box.textContent = HONESTY_LONG;
    }
  }

  function renderChips() {
    var el = document.getElementById("chips");
    var ids = rankedBenchmarks();
    var shown = mapScenarioId();
    el.innerHTML = ids.map(function (k) {
      return '<button type="button" aria-pressed="' + (shown === k) + '" data-chip="' + k + '">' +
        escapeHtml(CHIP_LABEL[k]) + "</button>";
    }).join("") +
      '<button type="button" aria-pressed="' + (shown === "package") + '" data-chip="all">All four</button>';
    el.querySelectorAll("[data-chip]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var k = btn.getAttribute("data-chip");
        mapId = k === "all" ? "package" : k;
        renderMap();
        renderTable();
        renderChart();
        renderCountyDetail();
        renderChips();
        renderKeyPoints();
        writeUrl();
        if (whyOpen) loadWhy();
      });
    });
  }

  function colorFor(value, maxAbs) {
    if (!maxAbs || value <= 0) return "#2a4d6e";
    var t = Math.sqrt(Math.max(0, Math.min(1, value / maxAbs)));
    var h = 210 - 165 * t;
    var s = 42 + 28 * t;
    var l = 28 + 30 * t;
    return "hsl(" + h + "," + s + "%," + l + "%)";
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

  function centroids() {
    return (geoDoc.counties || []).map(function (c) {
      var sx = 0, sy = 0, n = 0;
      (c.rings || []).forEach(function (ring) {
        ring.forEach(function (pt) { sx += pt[0]; sy += pt[1]; n += 1; });
      });
      return { fips: c.fips, x: n ? sx / n : 0, y: n ? sy / n : 0 };
    });
  }

  function neighborFips(fips, key) {
    var pts = centroids();
    var me = pts.filter(function (p) { return p.fips === fips; })[0];
    if (!me) return fips;
    var scored = pts.filter(function (p) { return p.fips !== fips; }).map(function (p) {
      var dx = p.x - me.x;
      var dy = p.y - me.y;
      var good = false;
      if (key === "ArrowRight") good = dx > 0 && Math.abs(dx) >= Math.abs(dy) * 0.25;
      if (key === "ArrowLeft") good = dx < 0 && Math.abs(dx) >= Math.abs(dy) * 0.25;
      if (key === "ArrowUp") good = dy > 0 && Math.abs(dy) >= Math.abs(dx) * 0.25;
      if (key === "ArrowDown") good = dy < 0 && Math.abs(dy) >= Math.abs(dx) * 0.25;
      return { fips: p.fips, d: dx * dx + dy * dy, good: good };
    }).filter(function (s) { return s.good; }).sort(function (a, b) { return a.d - b.d; });
    if (scored.length) return scored[0].fips;
    var names = geoDoc.counties.map(function (c) { return c.fips; });
    var i = names.indexOf(fips);
    if (key === "ArrowRight" || key === "ArrowDown") return names[(i + 1) % names.length];
    return names[(i - 1 + names.length) % names.length];
  }

  function chooseCounty(fips) {
    selectedFips = fips;
    if (walkStep === 2) walkStep = 3;
    renderMap();
    renderTable();
    renderChart();
    renderCountySelect();
    renderHeadline();
    renderCountyDetail();
    renderKeyPoints();
    if (whyOpen) loadWhy();
    writeUrl();
  }

  function renderMap() {
    if (!geoDoc) { mapStage.textContent = "Boundaries are still loading."; return; }
    mapTitle.textContent = locked.name + " counties";
    var box = projectBounds(geoDoc.counties);
    projBox = box;
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
      maxAbs = Math.max(maxAbs, Math.abs(countyMapValue(c)));
    });
    var paths = geoDoc.counties.map(function (c) {
      var row = countyRow(c.fips);
      var value = row ? countyMapValue(row) : 0;
      var d = (c.rings || []).map(function (ring) {
        return ring.map(function (pt, i) {
          var p = xy(pt[0], pt[1]);
          return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1);
        }).join(" ") + " Z";
      }).join(" ");
      var selected = c.fips === selectedFips;
      var label = escapeHtml(c.name) + " " + signed(value) + " calculated";
      var tab = selected || (!selectedFips && c.fips === geoDoc.counties[0].fips) ? 0 : -1;
      return '<path class="map-hit" data-fips="' + c.fips + '" d="' + d + '" tabindex="-1"></path>' +
        '<path class="county' + (selected ? " selected" : "") + '" role="img" data-fips="' +
        c.fips + '" tabindex="' + tab + '" d="' + d + '" fill="' + colorFor(value, maxAbs) +
        '"><title>' + label + "</title></path>";
    }).join("");
    mapStage.innerHTML = '<svg viewBox="0 0 ' + width + " " + height +
      '" role="group" aria-label="County map; same data as the table below">' +
      '<rect width="100%" height="100%" fill="transparent"></rect>' + paths + "</svg>";
    var nodes = Array.prototype.slice.call(mapStage.querySelectorAll("path.county"));
    nodes.forEach(function (node) {
      function choose() { chooseCounty(node.getAttribute("data-fips")); }
      node.setAttribute("aria-label", (countyRow(node.getAttribute("data-fips")) || {}).name || "");
      node.addEventListener("click", choose);
      node.addEventListener("focus", function () {
        renderCountyLine(node.getAttribute("data-fips"));
      });
      node.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          choose();
          setWhy(true);
          return;
        }
        if (event.key === "Home") {
          event.preventDefault();
          focusCounty(geoDoc.counties[0].fips);
          return;
        }
        if (event.key === "End") {
          event.preventDefault();
          focusCounty(geoDoc.counties[geoDoc.counties.length - 1].fips);
          return;
        }
        if (["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"].indexOf(event.key) < 0) return;
        event.preventDefault();
        focusCounty(neighborFips(node.getAttribute("data-fips"), event.key));
      });
    });
    mapStage.querySelectorAll("path.map-hit").forEach(function (hit) {
      hit.addEventListener("click", function () { chooseCounty(hit.getAttribute("data-fips")); });
    });
    renderCountyDetail();
  }

  function focusCounty(fips) {
    var nodes = mapStage.querySelectorAll("path.county");
    nodes.forEach(function (n) { n.tabIndex = n.getAttribute("data-fips") === fips ? 0 : -1; });
    var target = mapStage.querySelector('path.county[data-fips="' + fips + '"]');
    if (target) target.focus();
  }

  function renderCountyLine(fips) {
    var row = countyRow(fips);
    if (!row) return;
    var ids = selectedIds();
    var value = ids.length ? countyMapValue(row) : 0;
    var sid = mapScenarioId();
    var env = (sid && sid !== "selection") ? cell(row, sid) : null;
    var who = ids.length ? selectionLabel() + " " : "";
    var range = "";
    if (!ids.length) range = "";
    else if (env && isFinite(Number(env.p10)) && env.interval_status !== "reference") {
      range = " (likely " + integer(env.p10) + "–" + integer(env.p90) + ")";
    } else if (env && env.interval_status === "reference") {
      range = " (Reference range (defaults) " + integer(env.p10) + "–" + integer(env.p90) + ")";
    } else if (ids.length > 1 && sid === "selection") {
      range = " (" + HONESTY + ")";
    }
    var text = countyPhrase(row) + " " + who + signed(value) + " extra homes" + range +
      " on top of " + integer(cell(row, "baseline").central) + " expected.";
    countyDetail.hidden = false;
    countyDetail.textContent = text;
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
    var sid = mapScenarioId();
    if (!sid) {
      countyDetail.hidden = false;
      countyDetail.textContent = countyPhrase(row) + " 0 extra homes. No reforms selected.";
      return;
    }
    if (sid === "selection") {
      countyDetail.hidden = false;
      countyDetail.innerHTML =
        "<p>" + escapeHtml(countyPhrase(row)) + " " +
        escapeHtml(HONESTY) + ". Baseline " +
        bound("counties." + row.fips + ".results.baseline.central", integer(cell(row, "baseline").central)) +
        " expected.</p>";
      return;
    }
    var current = cell(row, sid);
    var env = lockedCell(row.fips, sid) || current;
    var pair = row.top_benchmark_pair;
    var cover = row.coverage || {};
    countyDetail.hidden = false;
    var prefix = "counties." + row.fips + ".results." + sid;
    countyDetail.innerHTML =
      "<p>" + escapeHtml(countyPhrase(row)) + " " +
      scenarioLabel(sid) + " " + bound(prefix + ".central", signed(countyMapValue(row))) + tag("calculated") +
      " (" + (env && env.interval_status === "reference" ? "Reference range (defaults) " : "Likely range ") +
      bound(prefix + ".p10", integer(env.p10)) + "–" + bound(prefix + ".p90", integer(env.p90)) +
      tag("assumed") + ") on top of " +
      bound("counties." + row.fips + ".results.baseline.central", integer(cell(row, "baseline").central)) +
      " expected " + tag("calculated") +
      ". Eligible " + bound(prefix + ".eligible", integer(current.eligible)) + tag("calculated") +
      ", feasible " + bound(prefix + ".feasible", integer(current.feasible)) + tag("calculated") +
      ". Local-rules range " + bound(prefix + ".zoning_low", integer(current.zoning_low)) + "–" +
      bound(prefix + ".zoning_high", integer(current.zoning_high)) + tag("calculated") +
      ". Census survey error ±" + bound(prefix + ".acs_moe", integer(current.acs_moe)) + tag("observed") +
      ". Local zoning known for " + bound("counties." + row.fips + ".coverage.adu", pct(cover.adu || 0)) +
      " of ADU lots " + tag("observed") +
      ". " + rankingBadge(pair, null, "counties." + row.fips + ".top_benchmark_pair.flip_share") + ".</p>";
  }

  function tableValue(row, key, sid) {
    var current = (sid && sid !== "selection") ? cell(row, sid) : null;
    if (key === "name") return row.name || "";
    if (key === "homes") return sid ? countyMapValue(row) : 0;
    if (!current) return null;
    if (key === "eligible") return current.eligible;
    if (key === "feasible") return current.feasible;
    if (key === "rules") return current.zoning_high;
    if (key === "census") return current.acs_moe;
    return 0;
  }

  function cellOrMissing(text, missing) {
    if (missing) return '<span class="missing">No data</span>';
    return text;
  }

  function renderTable() {
    var sid = mapScenarioId();
    var query = countyQuery.trim().toLowerCase();
    var rows = docCounties().slice().filter(function (row) {
      return !query || String(row.name || "").toLowerCase().indexOf(query) >= 0;
    });
    rows.sort(function (a, b) {
      var av = tableValue(a, tableSort.key, sid);
      var bv = tableValue(b, tableSort.key, sid);
      if (tableSort.key === "name") {
        return tableSort.dir === "asc" ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      }
      av = Number(av); bv = Number(bv);
      if (!isFinite(av)) av = -Infinity;
      if (!isFinite(bv)) bv = -Infinity;
      return tableSort.dir === "asc" ? av - bv : bv - av;
    });
    var visible = showAllCounties ? rows : rows.slice(0, 15);
    var caption = document.getElementById("county-caption");
    if (caption) {
      caption.textContent = "County model. " + (sid ? scenarioLabel(sid) : "No reform") +
        ". Extra homes, " + (endYearText() ? String(catalog.window_start).slice(0, 4) + "–" + endYearText() : "the window") + ".";
    }
    countyBody.innerHTML = visible.map(function (row) {
      var value = sid ? countyMapValue(row) : 0;
      var current = (sid && sid !== "selection") ? cell(row, sid) : null;
      var env = current ? (lockedCell(row.fips, sid) || current) : null;
      var prefix = "counties." + row.fips + ".results." + (sid || "baseline");
      var homesCell = !sid ? cellOrMissing("", true) : bound(prefix + ".central", signed(value));
      var rangeCell = env && isFinite(Number(env.p10))
        ? bound(prefix + ".p10", integer(env.p10)) + "–" + bound(prefix + ".p90", integer(env.p90))
        : cellOrMissing("", true);
      return "<tr data-fips='" + row.fips + "' class='" + (row.fips === selectedFips ? "selected" : "") + "'" +
        (row.fips === selectedFips ? " aria-current=\"true\"" : "") + ">" +
        "<th scope=\"row\">" + escapeHtml(row.name) + "</th>" +
        "<td>" + homesCell + (env ? " <span class=\"cell-range\">(" + rangeCell + ")</span>" : "") + "</td>" +
        "<td>" + (current ? bound(prefix + ".eligible", integer(current.eligible)) + " lots" : cellOrMissing("", true)) + "</td>" +
        "<td>" + (current ? bound(prefix + ".feasible", integer(current.feasible)) + " lots" : cellOrMissing("", true)) + "</td>" +
        "<td>" + (current ? bound(prefix + ".zoning_low", integer(current.zoning_low)) + "–" + bound(prefix + ".zoning_high", integer(current.zoning_high)) : cellOrMissing("", true)) + "</td>" +
        "<td>" + (current ? "±" + bound(prefix + ".acs_moe", integer(current.acs_moe)) : cellOrMissing("", true)) + "</td></tr>";
    }).join("");
    var cardsEl = document.getElementById("county-cards");
    if (cardsEl) {
      cardsEl.innerHTML = visible.map(function (row) {
        var current = (sid && sid !== "selection") ? cell(row, sid) : null;
        return '<article class="county-card"><h3>' + escapeHtml(row.name) + "</h3>" +
          "<p>Extra homes " + (sid ? signed(countyMapValue(row)) : "No data") + "</p>" +
          "<p>Eligible lots " + (current ? integer(current.eligible) : "No data") + "</p>" +
          "<p>Lots where it pays off " + (current ? integer(current.feasible) : "No data") + "</p></article>";
      }).join("");
    }
    var more = document.getElementById("show-all-counties");
    if (more) {
      var hiddenCount = rows.length - visible.length;
      more.hidden = hiddenCount <= 0 && !showAllCounties;
      more.textContent = showAllCounties ? "Show the first 15 counties" : "Show all " + rows.length + " counties";
    }
    var status = document.getElementById("county-filter-status");
    if (status) status.textContent = query ? (rows.length + " counties match.") : "";
    document.querySelectorAll("#county-table .sort").forEach(function (btn) {
      var key = btn.getAttribute("data-sort");
      if (key === tableSort.key) btn.setAttribute("aria-sort", tableSort.dir === "asc" ? "ascending" : "descending");
      else btn.removeAttribute("aria-sort");
    });
    countyBody.querySelectorAll("tr").forEach(function (tr) {
      tr.addEventListener("click", function () {
        chooseCounty(tr.getAttribute("data-fips"));
        setWhy(true);
      });
    });
  }

  function renderChart() {
    var stage = document.getElementById("chart-stage");
    if (!stage || !locked) return;
    var rows = docCounties().slice().sort(function (a, b) {
      return countyMapValue(b) - countyMapValue(a);
    }).slice(0, 15);
    var sid = mapScenarioId();
    var max = Math.max.apply(null, rows.map(function (r) {
      var env = lockedCell(r.fips, sid) || cell(r, sid);
      return Math.max(countyMapValue(r), env.p90 || 0);
    }).concat([1]));
    var W = 720, rowH = 28, H = 40 + rows.length * rowH;
    var bars = rows.map(function (row, i) {
      var v = countyMapValue(row);
      var env = (sid && sid !== "selection") ? (lockedCell(row.fips, sid) || cell(row, sid)) : null;
      var y = 24 + i * rowH;
      var x0 = 180, usable = 500;
      var x = x0 + Math.max(0, v) / max * usable;
      var lo = env ? x0 + Math.max(0, env.p10) / max * usable : x;
      var hi = env ? x0 + Math.max(0, env.p90) / max * usable : x;
      return '<text x="8" y="' + (y + 12) + '" font-size="12" fill="#1c2430">' +
        escapeHtml(row.name.replace(/ County$/, "")) + "</text>" +
        '<rect x="' + x0 + '" y="' + (y + 4) + '" width="' + Math.max(1, x - x0) +
        '" height="14" fill="#0e6e5c" rx="3"></rect>' +
        '<line x1="' + lo + '" x2="' + hi + '" y1="' + (y + 11) + '" y2="' + (y + 11) +
        '" stroke="#1d3557" stroke-width="2"></line>' +
        '<text x="' + (x + 8) + '" y="' + (y + 14) + '" font-size="11" fill="#4f5862">' +
        signed(v) + "</text>";
    }).join("");
    stage.innerHTML = '<svg viewBox="0 0 ' + W + " " + H +
      '" role="img" aria-label="Top 15 counties by extra homes, with likely-range whiskers">' +
      bars + "</svg>";
  }

  function setView(next, silent) {
    view = next;
    ["map", "table", "chart"].forEach(function (name) {
      var tab = document.getElementById("tab-" + name);
      var panel = document.getElementById("view-" + name);
      var onTab = name === view;
      if (tab) {
        tab.classList.toggle("active", onTab);
        tab.removeAttribute("aria-pressed");
        tab.setAttribute("aria-selected", onTab ? "true" : "false");
        tab.tabIndex = onTab ? 0 : -1;
      }
      if (panel && name !== "map") panel.hidden = !onTab;
    });
    if (!silent) writeUrl();
    if (view === "map" && !silent) {
      document.getElementById("map-stage").scrollIntoView({ behavior: RM ? "auto" : "smooth", block: "center" });
    }
  }

  function onViewTabKey(event) {
    var tabs = ["map", "table", "chart"];
    var i = tabs.indexOf(view);
    if (i < 0) i = 0;
    var next = i;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (i + 1) % tabs.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (i - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    setView(tabs[next]);
    var focus = document.getElementById("tab-" + tabs[next]);
    if (focus) focus.focus();
  }

  function sigFigs(n, digits) {
    var abs = Math.abs(n);
    if (!isFinite(abs) || abs === 0) return "0";
    var exp = Math.floor(Math.log10(abs));
    var places = Math.max(0, digits - 1 - exp);
    var rounded = Math.round(abs * Math.pow(10, places)) / Math.pow(10, places);
    return (n < 0 ? "−" : "") + rounded.toFixed(places);
  }

  function sliderValueText(spec, value) {
    var n = Number(value);
    if (!isFinite(n)) return "—";
    var unit = spec.unit || "";
    if (unit === "per year" || (Math.abs(n) > 0 && Math.abs(n) < 0.1 && unit.indexOf("share") < 0 && unit.charAt(0) !== "$")) {
      return sigFigs(n, 3) + (unit === "per year" ? " a year" : "");
    }
    if (unit === "share" || unit === "probability" || unit.indexOf("share") === 0) {
      return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 3 });
    }
    if (unit.charAt(0) === "$" || unit === "$ per home" || unit === "$ per sq ft") return money(value);
    if (Math.abs(n) >= 1000) return integer(n);
    var digits = Math.abs(n) >= 10 ? 2 : 3;
    return n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: digits });
  }

  function formatParam(spec, value) {
    return sliderValueText(spec, value);
  }

  function assumptionFigure(unit, value) {
    var text = sliderValueText({ unit: unit || "" }, value);
    if (!unit || text.indexOf("a year") >= 0 || text.indexOf(unit) >= 0) return text;
    if (unit.charAt(0) === "$") {
      var tail = unit.replace(/^\$\s*/, "");
      return tail ? text + " " + tail : text;
    }
    return text + " " + unit;
  }

  function renderSliders() {
    if (!catalog) return;
    var groups = {};
    catalog.parameters.forEach(function (p) {
      groups[p.group] = groups[p.group] || [];
      groups[p.group].push(p);
    });
    var keys = Object.keys(groups);
    if (on.has("parking")) {
      keys = keys.filter(function (group) { return group !== "parking"; });
      keys.unshift("parking");
    }
    var api = frameApi();
    var sid = headlineSid();
    var ranks = {};
    if (api && sid && locked) {
      api.rankDrivers(locked.statewide.one_at_a_time, sid, catalog.parameters).forEach(function (row, index) {
        ranks[row.key] = index + 1;
      });
    }
    sliders.innerHTML = keys.map(function (group) {
      var inner = groups[group].map(function (p) {
        var value = overrides.hasOwnProperty(p.name) ? overrides[p.name] : p.central;
        var step = (p.high - p.low) / 40;
        var id = "lab-slider-" + p.name;
        var label = api ? api.plainLabel(p.name, p.label) : p.label;
        var rankNote = ranks[p.name]
          ? '<p class="rank-note">Ranked #' + ranks[p.name] + " at default settings for " + escapeHtml(scenarioLabel(sid)) + ".</p>"
          : "";
        var changed = overrides.hasOwnProperty(p.name) ? '<p class="you-changed">you changed this</p>' : "";
        var valueText = sliderValueText(p, value);
        if (p.unit && valueText.indexOf("a year") < 0 && valueText.indexOf(p.unit) < 0) valueText += " " + p.unit;
        return '<div class="slider"><label for="' + id + '"><span>' + escapeHtml(label) + tag("assumed") +
          "</span><span>" + (Number(value) === Number(p.central)
            ? bound("by_name." + p.name + ".central", formatParam(p, value))
            : '<span data-derived="override" data-from="by_name.' + p.name + '.central">' +
              escapeHtml(formatParam(p, value)) + "</span>") + "</span></label>" +
          '<input id="' + id + '" type="range" min="' + p.low + '" max="' + p.high + '" step="' + step +
          '" value="' + value + '" data-name="' + p.name +
          '" aria-valuetext="' + escapeHtml(valueText) + '">' +
          rankNote + changed +
          '<p class="hint">' + escapeHtml(p.rationale) + "</p></div>";
      }).join("");
      var heading = api ? api.groupHeading(group) : group;
      var open = on.has("parking") && group === "parking" ? " open" : "";
      return "<details class='slider-group'" + open + "><summary>" + escapeHtml(heading) + "</summary>" + inner + "</details>";
    }).join("");
    sliders.querySelectorAll("input[type=range]").forEach(function (input) {
      input.addEventListener("input", function () {
        var name = input.getAttribute("data-name");
        var spec = catalog.parameters.filter(function (p) { return p.name === name; })[0];
        var next = Number(input.value);
        if (Math.abs(next - Number(spec.central)) < 1e-12) delete overrides[name];
        else overrides[name] = next;
        input.setAttribute("aria-valuetext", sliderValueText(spec, next));
        if (walkStep === 4) walkStep = 5;
        writeUrl();
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
      appliedOverrides = {};
      envelopeNote.textContent = drawsNote();
      renderAll();
      if (whyOpen) loadWhy();
      setStatus("");
      return;
    }
    var id = ++requestId;
    post("/api/lab/recompute", { state: stateCode, overrides: overrides, county: selectedFips }).then(function (doc) {
      if (id !== requestId) return;
      live = doc;
      appliedOverrides = {};
      Object.keys(doc.overrides || overrides).forEach(function (name) {
        appliedOverrides[name] = (doc.overrides || overrides)[name];
      });
      envelopeNote.textContent = doc.envelope_note;
      renderAll();
      if (whyOpen) loadWhy();
      var t = packageTotal();
      setStatus("Updated. Middle estimate " + signed(t.c) + ". Reference range — from default assumptions, not recomputed.");
    }).catch(function (err) {
      if (id !== requestId) return;
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

  function whyRequest() {
    var ids = selectedIds().slice();
    unknownOn.forEach(function (id) {
      if (ids.indexOf(id) < 0) ids.push(id);
    });
    var sid = "selection";
    if (!unknownOn.length) {
      if (ids.length === 4) sid = "package";
      else if (ids.length === 1) sid = ids[0];
    }
    return {
      state: stateCode,
      county: selectedFips,
      scenario: sid,
      reforms: ids,
      overrides: overrides
    };
  }

  function loadWhy() {
    if (!selectedFips) { whyBody.innerHTML = "<p>Pick a county.</p>"; return; }
    post("/api/lab/why", whyRequest()).then(function (doc) {
      whyDoc = doc;
      renderWhy();
      renderKeyPoints();
      renderSources();
    }).catch(function () {
      whyBody.textContent = "";
      whyBody.appendChild(document.createTextNode("Couldn't load this explanation. "));
      var retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "Retry";
      retry.addEventListener("click", loadWhy);
      whyBody.appendChild(retry);
    });
  }

  function funnelCell(stage, name) {
    if (!stage) return "—";
    var value = stage[name];
    if (value === null || value === undefined || value === "") return "—";
    var n = Number(value);
    if (!isFinite(n)) return "—";
    if (name === "completion" || name === "timing" || name === "homes_per_lot" || name === "go_ahead_share") {
      return (100 * n).toFixed(1) + "%";
    }
    return integer(n);
  }

  function renderLotFunnel(whyDoc) {
    var funnel = whyDoc.result && whyDoc.result.funnel;
    var api = frameApi();
    if (api) {
      var sid = whyDoc.scenario;
      var fips = whyDoc.county && whyDoc.county.fips;
      return api.funnelHtml({
        sid: sid,
        funnel: funnel,
        stateName: locked ? locked.name : "",
        label: scenarioLabel(sid),
        endYear: endYearText(),
        prefix: fips ? "counties." + fips + ".results." + sid + ".funnel" : "statewide.results." + sid + ".funnel",
        middle: whyDoc.result && whyDoc.result.delivery,
        middlePath: fips ? "counties." + fips + ".results." + sid + ".central" : "statewide.results." + sid + ".central",
        low: null,
        high: null,
        feesLotHomes: whyDoc.result && whyDoc.result.host_delta,
        feesPath: fips ? "counties." + fips + ".results.fees.host_delta" : "statewide.results.fees.host_delta",
        collapseSteps: window.matchMedia && window.matchMedia("(max-width: 600px)").matches
      });
    }
    if (!funnel) {
      if (whyDoc.scenario === "parking" || whyDoc.scenario === "fees") {
        return "<h3>Lot funnel</h3><p>Not modelled for this reform: this reform changes costs for projects, not what is legal.</p>";
      }
      return "";
    }
    var names = ["legal_fits", "pays", "go_ahead", "finishing", "completion", "delivered"];
    var labels = {
      legal_fits: "Lots where a legal option fits",
      pays: "Lots that clear the hurdle",
      go_ahead: "Lots that start in time",
      finishing: "Lots that finish by year 5",
      completion: "Completion ratio",
      delivered: "Homes delivered"
    };
    var body = names.map(function (name) {
      return "<tr><th scope='row'>" + labels[name] + "</th><td>" + funnelCell(funnel.gross, name) +
        "</td><td>" + funnelCell(funnel.baseline_gross, name) + "</td><td>" + funnelCell(funnel, name) + "</td></tr>";
    }).join("");
    return "<h3>Lot funnel</h3><p class='help'>The chart is the reform world against the baseline world. " +
      "The incremental column is the difference, same as the result. Completion is the never-complete share for the lots that were chosen. " +
      "Best use is one option per lot.</p>" +
      "<table><caption class='visually-hidden'>Lot funnel, reform world against baseline</caption>" +
      "<thead><tr><th scope='col'>Stage</th><th scope='col'>Reform world</th><th scope='col'>Baseline world</th><th scope='col'>Incremental</th></tr></thead><tbody>" +
      body + "</tbody></table>";
  }

  function renderWhy() {
    if (!whyDoc) return;
    if (whyDoc.empty) {
      whyBody.innerHTML = "<p>No reforms selected. Turn one on to see why this county would change.</p>";
      return;
    }
    if (whyDoc.per_reform && whyDoc.per_reform.length) {
      var lines = whyDoc.per_reform.map(function (part) {
        return "<li>" + escapeHtml(scenarioLabel(part.id)) + ": " + signed(part.delivery) +
          " extra homes, eligible " + integer(part.eligible) + ", feasible " + integer(part.feasible) + ".</li>";
      }).join("");
      whyBody.innerHTML =
        "<h3>Why this selection</h3><p>" + escapeHtml(whyDoc.note || "") + "</p><ul>" + lines +
        "</ul><p>Together, added together, not modeled as a package: " +
        signed(whyDoc.result.delivery) +
        " extra homes. Eligible " + integer(whyDoc.result.eligible) +
        ", feasible " + integer(whyDoc.result.feasible) +
        " (sum of per-reform counts; lots may overlap; not a joint count).</p>";
      return;
    }
    var sw = docStatewide();
    var decomp = (live && live.county && live.county.package_decomposition) || whyDoc.package_decomposition;
    var wwc = locked.statewide.what_would_change;
    var inputs = whyDoc.inputs.map(function (row) {
      var moneyish = row.id.indexOf("rent") >= 0 || row.id.indexOf("value") >= 0 || row.id === "hud_fmr_1br";
      return '<div class="receipt-row"><span>' + escapeHtml(row.label) + tag(row.tag) +
        "</span><span>" + (moneyish ? money(row.value) : integer(row.value)) +
        (row.moe ? " ±" + integer(row.moe) : "") +
        '</span><span class="src">' + escapeHtml(row.source || "") + "</span></div>";
    }).join("");
    var assumptions = whyDoc.assumptions.map(function (row) {
      return '<div class="receipt-row"><span>' + escapeHtml(row.label) + tag("assumed") +
        (row.locked ? " (Handbook locked)" : "") +
        "</span><span>" + formatParam({ unit: row.unit }, row.value) +
        '</span><span class="src">' + escapeHtml(row.rationale || "") + "</span></div>";
    }).join("");
    var options = whyDoc.options.map(function (row) {
      return '<div class="stat"><div class="k">' + row.option + (row.illustrative ? " · illustrative" : "") +
        tag("calculated") + "</div><div class='s'>value " + money(row.value) + " · cost " + money(row.cost) +
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
    var heading = "Why " + whyDoc.county.name + " gets about " + signed(whyDoc.result.delivery) + " homes";
    whyBody.innerHTML =
      "<h3 id='why-heading' tabindex='-1'>" + escapeHtml(heading) + "</h3>" +
      "<p>Most of the increment is existing homes that become legal and then pencil out, not teardowns. " +
      signed(whyDoc.result.delivery) + tag("calculated") +
      ". Host term " + signed(whyDoc.result.host_delta) + ", pipeline " + signed(whyDoc.result.pipeline_delta) + ".</p>" +
      renderLotFunnel(whyDoc) +
      (whyDoc.lots_note ? "<p class='help'>" + escapeHtml(whyDoc.lots_note) + "</p>" : "") +
      (whyDoc.imputed.length ? "<p class='help'>Imputed ACS fields, never zero: " + escapeHtml(whyDoc.imputed.join(", ")) + ".</p>" : "") +
      "<h3>Inputs</h3><div class='receipt'>" + inputs + "</div>" +
      "<h3>Assumptions used</h3><div class='receipt'>" + assumptions + "</div>" +
      "<h3>Illustrative urban detached cost-and-value worksheet</h3><p class='help'>" + escapeHtml(whyDoc.option_note) + "</p>" +
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
      " is 10 percent of draws.</p><ul>" + switches + "</ul>" +
      (frameApi() ? frameApi().limitsHtml({
        sid: whyDoc.scenario === "package" || BENCHMARKS.indexOf(whyDoc.scenario) >= 0 ? whyDoc.scenario : headlineSid(),
        drivers: frameApi().rankDrivers(locked.statewide.one_at_a_time, headlineSid() || whyDoc.scenario, catalog ? catalog.parameters : []),
        driverSid: headlineSid() || whyDoc.scenario,
        ratios: catalog && catalog.completion_ratios,
        low: (docStatewide().results[whyDoc.scenario] || {}).p10,
        high: (docStatewide().results[whyDoc.scenario] || {}).p90,
        baseline: docStatewide().results.baseline.central,
        lowPath: "statewide.results." + whyDoc.scenario + ".p10",
        highPath: "statewide.results." + whyDoc.scenario + ".p90",
        parkingText: paramText("parking_market_urban"),
        parkingPath: "by_name.parking_market_urban.central"
      }) : "");
    var head = document.getElementById("why-heading");
    if (head) head.focus();
  }

  function renderKeyPoints() {
    var list = document.getElementById("keypoints-list");
    if (!list || !locked) return;
    var sid = mapScenarioId();
    if (!sid || sid === "selection") {
      list.innerHTML = "<li>" + (!sid
        ? "No reforms selected."
        : "This mix is the sum of the selected reforms. Eligible and feasible in the Why drawer are that sum, not a joint count. A likely range is available for one reform or all four.") + "</li>";
      return;
    }
    var row = selectedFips ? countyRow(selectedFips) : null;
    var current = row ? cell(row, sid) : docStatewide().results[sid];
    var eligible = current.eligible;
    var feasible = current.feasible;
    var ratio = eligible ? feasible / eligible : 0;
    var wwc = locked.statewide.what_would_change;
    var switch0 = wwc && wwc.switches && wwc.switches[0];
    var host = (row ? cell(row, sid) : docStatewide().results[sid]).host_delta;
    var basePath = row ? "counties." + row.fips + ".results." + sid : "statewide.results." + sid;
    var hostLine = "<li>Most of the gain comes from converting existing homes, not teardowns. Host term " +
      bound(basePath + ".host_delta", signed(host)) + ". " + tag("calculated") + "</li>";
    var lotLine = eligible
      ? "<li>Fewer than 1 in " + (ratio > 0 ? Math.max(1, Math.round(1 / ratio)) : "all") +
        " lots where it becomes legal also pencil out (" +
        bound(basePath + ".feasible", integer(feasible)) + " of " +
        bound(basePath + ".eligible", integer(eligible)) + "). " + tag("calculated") + "</li>"
      : "<li>Eligible and feasible counts come from the locked county run.</li>";
    var flipLine = switch0
      ? "<li>The result is most sensitive to " + escapeHtml(switch0.label.toLowerCase()) +
        ". Order can flip at " +
        bound("statewide.what_would_change.switches.0.switch_at", assumptionFigure(switch0.unit, switch0.switch_at)) +
        ". " + tag("calculated") + "</li>"
      : "<li>The ranking can move when a published assumption changes.</li>";
    list.innerHTML = hostLine + lotLine + flipLine;
  }

  function renderSources() {
    var el = document.getElementById("sources-body");
    if (!el || !locked) return;
    var cover = locked.coverage || {};
    el.innerHTML =
      "<ul>" +
      "<li>ACS 2020–2024 5-year county tables B25001, B25024, B25031, B25077 " + tag("observed") + "</li>" +
      "<li>Census Building Permits Survey 2023–2025 county files " + tag("observed") + "</li>" +
      "<li>Census cartographic boundary file cb_2024_us_county_5m, simplified " + tag("observed") + "</li>" +
      "<li>Published assumption bands in config/lab/assumptions.yaml " + tag("assumed") + "</li>" +
      "<li>ADU evidence coverage " + bound("coverage.adu", pct(cover.adu)) +
      " · 2–6-home evidence " + bound("coverage.mm", pct(cover.mm)) + " " + tag("calculated") + "</li>" +
      "</ul>" +
      "<p class='help'>Full vintages: docs/DATA_PROVENANCE.md. The Why drawer lists the source on each row.</p>";
  }

  function loadChecked() {
    var el = document.getElementById("checked-live");
    if (!el) return;
    el.textContent = "Loading the parcel-informed comparison…";
    post("/api/crossval", { scope: "tier1", draws: 20 }).then(function (doc) {
      var parts = Object.keys(doc.states || {}).map(function (code) {
        var block = doc.states[code].scenarios || {};
        var scenario = block.adu ? "adu" : "missing_middle";
        var first = block[scenario] || {};
        var err = first.imputed_parcels && first.imputed_parcels.percent_error;
        if (err == null) return escapeHtml(code);
        var text = (err > 0 ? "+" : "") + Number(err).toFixed(1) + "%";
        var path = "crossval_tier1." + code + ".percent_error";
        return escapeHtml(code) + ' <span data-bind="' + path + '">' + text + "</span>";
      });
      el.innerHTML = "Error vs. parcel data on the states that have extracts: " +
        (parts.join(" · ") || "see Cross-check on the screening view") +
        " " + tag("calculated") + ". " + escapeHtml(doc.note || "");
    }).catch(function () {
      el.textContent = "Open the screening view Cross-check tab to run the comparison on CT, WI, UT, and HI.";
    });
  }

  function renderBrief() {
    var el = document.getElementById("brief-print");
    if (!el || !locked) return;
    var sw = docStatewide();
    var t = packageTotal();
    var rank = rankedBenchmarks();
    var rangeHead = (sw.results.adu && sw.results.adu.interval_status === "reference")
      ? "Reference range (defaults)" : "Likely range";
    var rows = rank.map(function (k) {
      var r = sw.results[k];
      return "<tr><td>" + escapeHtml(PLAIN[k]) + "</td><td>" + signed(r.central) +
        "</td><td>" + describeRange(r) + "</td></tr>";
    }).join("");
    var d = sw.package_decomposition;
    var api = frameApi();
    var opts = headlineOpts();
    var head = api ? api.headlineParts(opts).html : "<h1>" + escapeHtml(answerLine()) + "</h1>";
    var sid = headlineSid();
    var limits = api && sid ? api.limitsHtml({
      sid: sid,
      drivers: api.rankDrivers(locked.statewide.one_at_a_time, sid, catalog ? catalog.parameters : []),
      driverSid: sid,
      ratios: catalog && catalog.completion_ratios,
      low: opts.low,
      high: opts.high,
      baseline: opts.baseline,
      lowPath: opts.paths.low,
      highPath: opts.paths.high,
      parkingText: paramText("parking_market_urban"),
      parkingPath: "by_name.parking_market_urban.central"
    }) : "<p>What this can't tell you: it does not say which lots will build.</p>";
    el.innerHTML =
      '<p class="model-badge county">County model · county by county · PA, NH</p>' +
      "<p>Stateframe brief — " + escapeHtml(locked.name) + ", " +
      escapeHtml(String(catalog && catalog.window_start || "").slice(0, 4)) + "–" + escapeHtml(endYearText()) +
      ". " + escapeHtml(locked.generated || "") + ". " + escapeHtml(locked.fingerprint || "") + ".</p>" +
      head +
      "<table><thead><tr><th>Reform</th><th>Middle estimate</th><th>" + escapeHtml(rangeHead) + "</th></tr></thead><tbody>" +
      rows +
      "<tr><td>All four together (don't add the bills up)</td><td>" + signed(d.package) +
      "</td><td>" + integer(sw.results.package.p10) + "–" + integer(sw.results.package.p90) +
      "</td></tr></tbody></table>" +
      "<p>" + (mixUnranked()
        ? "Close call applies to one reform or all four."
        : escapeHtml(rankingLine(sw)) + ". " +
          (sw.top_benchmark_pair.close_call ? "Too close to call." : "Ranking holds.")) + "</p>" +
      "<p>Also modeled, not a Handbook benchmark: by-right approval with a shot clock, " +
      signed(sw.results.approval.central) + ".</p>" +
      (on.has("parking") && api ? api.parkingHtml({
        show: true,
        urbanText: paramText("parking_market_urban"),
        minText: paramText("parking_min_urban")
      }) : "") +
      limits +
      (api ? api.modelDiffHtml(catalog && catalog.completion_ratios) : "") +
      (catalog && catalog.reconciliation_note ? "<p>" + escapeHtml(catalog.reconciliation_note) + "</p>" : "") +
      "<p>" + escapeHtml(location.href.split("#")[0]) + "</p>";
    void t;
  }

  function renderDrivers() {
    var mount = document.getElementById("drivers-mount");
    var api = frameApi();
    if (!mount || !api || !locked) return;
    var sid = headlineSid();
    mount.innerHTML = api.driversHtml({
      sid: sid,
      label: sid ? scenarioLabel(sid) : "",
      oat: locked.statewide.one_at_a_time,
      params: catalog ? catalog.parameters : [],
      showAll: showAllDrivers,
      hasOverrides: Object.keys(overrides).length > 0,
      changed: overrides,
      switches: (locked.statewide.what_would_change && locked.statewide.what_would_change.switches) || [],
      formatFigure: function (unit, value) {
        return assumptionFigure(unit, value);
      }
    });
    var limitIds = sid ? [sid] : selectedIds();
    limitIds.forEach(function (limitId) {
      var row = docStatewide().results[limitId];
      if (!row) return;
      var prefix = "statewide.results." + limitId;
      mount.insertAdjacentHTML("beforeend", api.limitsHtml({
        sid: limitId,
        drivers: api.rankDrivers(locked.statewide.one_at_a_time, limitId, catalog ? catalog.parameters : []),
        driverSid: limitId,
        ratios: catalog && catalog.completion_ratios,
        low: row.p10,
        high: row.p90,
        baseline: docStatewide().results.baseline.central,
        lowPath: prefix + ".p10",
        highPath: prefix + ".p90",
        parkingText: paramText("parking_market_urban"),
        parkingPath: "by_name.parking_market_urban.central"
      }));
    });
  }

  function renderModelDiff() {
    var el = document.getElementById("model-diff");
    var api = frameApi();
    if (!el || !api) return;
    el.innerHTML = api.modelDiffHtml(catalog && catalog.completion_ratios);
  }

  function renderWalk() {
    var step = WALK[walkStep];
    var prog = document.getElementById("walk-progress");
    var text = document.getElementById("walk-text");
    if (!prog || !text || !step) return;
    prog.textContent = "Step " + (walkStep + 1) + " of " + WALK.length + ". " + step.title;
    text.textContent = step.text;
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

  function tryPennsylvania() {
    stateCode = "PA";
    on = new Set(BENCHMARKS);
    scenarioId = "package";
    mapId = "package";
    selectedFips = "42003";
    view = "map";
    writeUrl();
    var go = function () {
      renderAll();
      var target = document.getElementById("hero");
      if (target) target.scrollIntoView({ behavior: RM ? "auto" : "smooth", block: "start" });
    };
    if (!locked || locked.state !== "PA") loadAll().then(go);
    else go();
  }

  function copyView() {
    writeUrl();
    var url = location.href;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(function () { setStatus("Copied link to this view."); });
    } else {
      setStatus(url);
    }
  }

  function downloadBlob(blob, name) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
  }

  function exportPng() {
    var svg = view === "chart"
      ? document.querySelector("#chart-stage svg")
      : document.querySelector("#map-stage svg");
    if (!svg) { setStatus("Nothing to draw yet."); return; }
    var xml = new XMLSerializer().serializeToString(svg);
    var blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var img = new Image();
    img.onload = function () {
      var canvas = document.createElement("canvas");
      canvas.width = Math.max(800, img.width * 2);
      canvas.height = Math.max(400, img.height * 2);
      var ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fbf6ec";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(function (out) {
        downloadBlob(out, "stateframe-" + stateCode + "-" + view + ".png");
        URL.revokeObjectURL(url);
      });
    };
    img.src = url;
  }

  function exportCsv() {
    var stamp = document.querySelector(".build-stamp");
    var sha = stamp ? String(stamp.textContent || "").replace(/^Build\s*/, "").split("·")[0].trim() : "";
    var text = buildCountyCsv(docCounties(), selectedIds(), {
      live: !!live,
      lockedCounties: locked ? locked.counties : [],
      model: "county",
      seed: locked && locked.seed,
      fingerprint: locked && locked.fingerprint,
      sha: sha,
      overrides: encodeOverrides(appliedOverrides)
    });
    downloadBlob(new Blob([text], { type: "text/csv" }), "stateframe-" + stateCode + "-counties.csv");
  }

  function printBrief() {
    renderBrief();
    window.print();
  }

  function download(fmt) {
    var payload = {
      state: stateCode,
      format: fmt,
      county: selectedFips,
      overrides: overrides,
      reforms: selectedIds()
    };
    fetch("/api/lab/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (!res.ok) throw new Error("export failed");
      var name = (res.headers.get("Content-Disposition") || 'filename="lab-brief"').replace(/.*filename="?([^"]+)"?.*/, "$1");
      return res.blob().then(function (blob) { return { blob: blob, name: name }; });
    }).then(function (file) {
      downloadBlob(file.blob, file.name);
    }).catch(function () { showRetry(function () { download(fmt); }); });
  }

  function showTour(i) {
    var el = document.getElementById("tour");
    if (i >= TOUR_STEPS.length) {
      el.hidden = true;
      try { localStorage.setItem(TOUR_KEY, "1"); } catch (err) {}
      if (lastFocus) lastFocus.focus();
      return;
    }
    tourIndex = i;
    el.hidden = false;
    document.getElementById("tour-dots").innerHTML = TOUR_STEPS.map(function (_, j) {
      return '<i class="' + (j <= i ? "on" : "") + '"></i>';
    }).join("");
    document.getElementById("tour-title").textContent = (i + 1) + " of " + TOUR_STEPS.length + " · " + TOUR_STEPS[i][0];
    document.getElementById("tour-text").textContent = TOUR_STEPS[i][1];
    document.getElementById("tour-next").textContent = i === TOUR_STEPS.length - 1 ? "Done" : "Next";
    document.getElementById("tour-title").focus();
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

  if (window.StateframeFmt) {
    window.StateframeFmt.bindTips(document);
  } else {
    document.addEventListener("click", function (event) {
      var btn = event.target.closest ? event.target.closest("button.tip") : null;
      if (!btn) {
        closeTips();
        return;
      }
      event.preventDefault();
      var open = btn.getAttribute("aria-expanded") === "true";
      closeTips();
      if (!open) {
        btn.setAttribute("aria-expanded", "true");
        var pop = document.getElementById(btn.getAttribute("aria-describedby"));
        if (pop) pop.hidden = false;
      }
    });
    document.addEventListener("focusin", function (event) {
      var btn = event.target.closest ? event.target.closest("button.tip") : null;
      if (!btn) return;
      closeTips();
      btn.setAttribute("aria-expanded", "true");
      var pop = document.getElementById(btn.getAttribute("aria-describedby"));
      if (pop) pop.hidden = false;
    });
  }
  document.addEventListener("click", function (event) {
    var moreDrivers = event.target.closest ? event.target.closest("#drivers-more") : null;
    if (moreDrivers) {
      showAllDrivers = !showAllDrivers;
      renderDrivers();
      return;
    }
    var adjust = event.target.closest ? event.target.closest(".driver-adjust") : null;
    if (adjust) {
      var name = adjust.getAttribute("data-driver");
      var input = document.getElementById("lab-slider-" + name);
      if (input) {
        var details = input.closest("details");
        if (details) details.open = true;
        input.focus();
      }
      return;
    }
    var showCounties = event.target.closest ? event.target.closest("#show-all-counties") : null;
    if (showCounties) {
      showAllCounties = !showAllCounties;
      renderTable();
      return;
    }
    var sortBtn = event.target.closest ? event.target.closest(".sort") : null;
    if (sortBtn) {
      var key = sortBtn.getAttribute("data-sort");
      if (tableSort.key === key) tableSort.dir = tableSort.dir === "asc" ? "desc" : "asc";
      else tableSort = { key: key, dir: key === "name" ? "asc" : "desc" };
      renderTable();
    }
  });
  var countyFind = document.getElementById("county-find");
  if (countyFind) {
    countyFind.addEventListener("input", function () {
      countyQuery = countyFind.value || "";
      renderTable();
    });
  }
  whyToggle.addEventListener("click", function () {
    setWhy(!whyOpen);
  });
  document.getElementById("why-close").addEventListener("click", function () {
    setWhy(false);
  });
  document.getElementById("why-adjust").addEventListener("click", function () {
    document.getElementById("adjust").scrollIntoView({ behavior: RM ? "auto" : "smooth" });
  });
  document.addEventListener("focusin", function (event) {
    var bar = document.getElementById("mini-total");
    var node = event.target;
    if (!bar || bar.hidden || !node || typeof node.getBoundingClientRect !== "function") return;
    if (bar.contains(node)) return;
    var barBox = bar.getBoundingClientRect();
    if (barBox.height < 8) return;
    var box = node.getBoundingClientRect();
    var gap = 12;
    if (box.top >= barBox.bottom + gap) return;
    window.scrollTo({
      top: window.scrollY + box.top - barBox.bottom - gap,
      behavior: "instant"
    });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      if (document.querySelector("button.tip[aria-expanded='true']")) {
        event.preventDefault();
        closeTips();
        return;
      }
      if (!document.getElementById("tour").hidden) {
        event.preventDefault();
        showTour(99);
        return;
      }
      if (whyOpen) {
        event.preventDefault();
        setWhy(false);
      }
    }
  });

  if (countySelect) {
    countySelect.addEventListener("change", function () {
      chooseCounty(countySelect.value);
    });
  }
  if (stateSelect) {
    stateSelect.addEventListener("change", function () {
      changeState(stateSelect.value);
    });
  }

  document.getElementById("reset").addEventListener("click", function () {
    overrides = {};
    live = null;
    envelopeNote.textContent = drawsNote();
    renderAll();
    if (whyOpen) loadWhy();
    setStatus("");
  });

  document.getElementById("export-md").addEventListener("click", function () {
    if (walkStep === 5) renderWalk();
    download("md");
  });
  document.getElementById("export-html").addEventListener("click", function () { download("html"); });
  document.getElementById("export-csv").addEventListener("click", function () { exportCsv(); });
  document.getElementById("export-png").addEventListener("click", exportPng);
  document.getElementById("export-pdf").addEventListener("click", printBrief);
  document.getElementById("print-brief").addEventListener("click", printBrief);
  document.getElementById("copy-view").addEventListener("click", copyView);
  document.getElementById("copy-view-where").addEventListener("click", copyView);
  document.getElementById("try-pa").addEventListener("click", tryPennsylvania);
  document.getElementById("tour-btn").addEventListener("click", function (event) {
    lastFocus = event.target;
    showTour(0);
  });
  document.getElementById("tour-next").addEventListener("click", function () { showTour(tourIndex + 1); });
  document.getElementById("tour-skip").addEventListener("click", function () { showTour(99); });
  ["map", "table", "chart"].forEach(function (name) {
    var tab = document.getElementById("tab-" + name);
    tab.addEventListener("click", function () { setView(name); });
    tab.addEventListener("keydown", onViewTabKey);
  });

  if (typeof window !== "undefined") {
    window.StateframeLab = {
      selection: function () { return selectedIds().slice(); },
      whyRequest: whyRequest,
      funnelCell: funnelCell,
      overrideMap: function () { return Object.assign({}, overrides); },
      describeRange: describeRange,
      writeUrl: writeUrl,
      buildCountyCsv: buildCountyCsv,
      sliderValueText: sliderValueText,
      tooltipMarkup: tipControl,
      decodeOverrides: decodeOverrides,
      mixColumns: MIX_CSV_COLUMNS.slice(),
      scenarioColumns: SCENARIO_CSV_COLUMNS.slice()
    };
  }

  parseUrl();
  renderStateNotice();
  var bootName = document.getElementById("state-name");
  if (bootName) bootName.textContent = stateNameOf(stateCode);
  if (stateSelect) stateSelect.value = stateCode;
  var q = new URLSearchParams(location.search);
  var shouldTry = q.get("try") === "1";
  loadAll().then(function () {
    if (shouldTry) tryPennsylvania();
    loadChecked();
  });
})();
