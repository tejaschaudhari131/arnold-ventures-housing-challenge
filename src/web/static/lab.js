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
  var HONESTY = "simple sum, not modeled; overlap can move it down or up";
  var HONESTY_LONG = "Simple sum shown, not modeled. Overlap can push the real total down (ADUs and 2–6 homes compete for the same lots) or up (fee and parking cuts help both).";
  var TOUR_STEPS = [
    ["This is the answer", "The big number is extra homes over five years from the reforms you pick. The bar under it is the likely range, never hidden."],
    ["Flip a reform", "Each card is one bill. Turn it on or off and watch the total and the map change."],
    ["Don't add the bills up", "Reforms overlap. This panel shows the modeled total next to the simple sum when all four are on."],
    ["Take it with you", "Print a one-page brief with your package and its range, or copy a link to this view."]
  ];
  var WALK = [
    { title: "Pennsylvania is loaded", text: "All 67 counties and four Handbook scenarios are already computed. Unknown zoning is a prior, never zero." },
    { title: "Pick a reform", text: "Start with a Handbook reform. The cards show the increment versus Baseline." },
    { title: "Open Allegheny County", text: "Allegheny is the walkthrough. Pittsburgh's October 2026 ADU ordinance is observed; the rest of the county is unknown." },
    { title: "Why this result?", text: "Every input is tagged observed, assumed, or calculated. The ADU pro forma is illustrative." },
    { title: "Change one assumption", text: "Move the homeowner uptake hazard. Central, zoning, and ACS MOE recompute. The p10–p90 envelope does not." },
    { title: "Export a brief", text: "Download Markdown, HTML, or a county CSV. The brief states the ranking, including a tie when draw medians disagree with the central order, and what would change it." }
  ];
  var TIPS = {
    "pro forma": "A simple cost-and-value worksheet for one building type.",
    "uptake hazard": "The yearly chance a feasible lot actually starts a project.",
    prior: "A published guess used when a local rule has not been read.",
    Envelope: "The likely range from 2,000 test runs of the published assumptions.",
    Zoning: "How the answer moves if unknown local rules are more or less strict.",
    "ACS MOE": "Census survey error on the counts and prices that feed the model."
  };
  var RM = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var TOUR_KEY = "sf-lab-tour-v2";

  var stateCode = "PA";
  var scenarioId = "missing_middle";
  var selectedFips = "42003";
  var on = new Set(["missing_middle"]);
  var view = "map";
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
  var shown = 0;
  var lastFocus = null;
  var tourIndex = 0;
  var projBox = null;

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
  var stateSelect = document.getElementById("state-select");

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
    if (ids.length === 1) return ids[0];
    if (ids.length === 4) return "package";
    if (on.has(scenarioId) && BENCHMARKS.indexOf(scenarioId) >= 0) return scenarioId;
    return ids[0] || "missing_middle";
  }

  function packageTotal() {
    var ids = selectedIds();
    var sw = docStatewide().results;
    if (!ids.length) return { c: 0, lo: 0, hi: 0, exact: true };
    if (ids.length === 1) {
      var one = sw[ids[0]];
      return { c: one.central, lo: one.p10, hi: one.p90, exact: true };
    }
    if (ids.length === 4) {
      var pack = sw.package;
      return { c: pack.central, lo: pack.p10, hi: pack.p90, exact: true };
    }
    var sum = ids.reduce(function (a, k) { return a + Number(sw[k].central); }, 0);
    return { c: sum, lo: null, hi: null, exact: false };
  }

  function countyPackageValue(row) {
    var ids = selectedIds();
    if (!ids.length) return 0;
    if (ids.length === 4) return cell(row, "package").central;
    return ids.reduce(function (a, k) { return a + Number(cell(row, k).central); }, 0);
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

  function parseUrl() {
    var q = new URLSearchParams(location.search);
    var st = (q.get("st") || "").toUpperCase();
    if (st === "PA" || st === "NH") stateCode = st;
    var raw = q.get("on");
    if (raw) {
      on = new Set();
      raw.split(",").forEach(function (part) {
        var id = ALIAS[part] || part;
        if (BENCHMARKS.indexOf(id) >= 0) on.add(id);
      });
      if (!on.size) on.add("missing_middle");
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
    q.set("on", selectedIds().map(function (id) { return SHORT[id]; }).join(","));
    if (selectedFips) q.set("county", selectedFips);
    q.set("view", view);
    history.replaceState(null, "", "?" + q.toString() + location.hash);
  }

  function fillAduFeeNote() {
    var el = document.getElementById("adu-fee-note");
    if (!el || !aduCompare) return;
    el.innerHTML = aduCompare.notes.lab_html;
  }

  function loadAll() {
    var id = ++requestId;
    setStatus("Loading " + (stateCode === "PA" ? "Pennsylvania's 67 counties" : "New Hampshire's 10 counties") + "…");
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
      if (stateSelect) stateSelect.value = stateCode;
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
    renderRecon();
    setView(view, true);
    writeUrl();
  }

  function renderStates() {
    if (!stateList) return;
    stateList.innerHTML = ["PA", "NH"].map(function (code) {
      var name = code === "PA" ? "Pennsylvania" : "New Hampshire";
      var role = code === "PA" ? "primary" : "portability";
      return '<button type="button" class="state-btn' + (code === stateCode ? " active" : "") +
        '" data-state="' + code + '"><strong>' + name + "</strong><span>" + role + "</span></button>";
    }).join("");
    stateList.querySelectorAll("[data-state]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        changeState(btn.getAttribute("data-state"));
      });
    });
  }

  function changeState(code) {
    stateCode = code;
    selectedFips = code === "PA" ? "42003" : null;
    walkStep = 0;
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
    return scenarioLabel(pair.leader) + " ≈ " + scenarioLabel(pair.trailer) +
      "; " + scenarioLabel(pair.trailer) + " ahead in " + Math.round(pair.flip_share * 100) +
      "% of draws (draw medians " + medianShort(pair.trailer) + " " + integer(trail.p50) +
      " vs " + medianShort(pair.leader) + " " + integer(lead.p50) + ")";
  }

  function rankingLine(sw) {
    var rank = sw.benchmark_ranking || [];
    if (isDrawTie(sw.top_benchmark_pair) && rank.length >= 2) {
      return scenarioLabel(rank[0]) + " ≈ " + scenarioLabel(rank[1]) +
        (rank.length > 2 ? " > " + rank.slice(2).map(scenarioLabel).join(" > ") : "");
    }
    return rank.map(scenarioLabel).join(" > ");
  }

  function rankingBadge(pair, sw) {
    var threshold = (locked && locked.close_call_flip_share_label) || "close-call threshold";
    if (!pair || !pair.close_call) {
      return '<span class="badge-holds">Ranking holds</span>';
    }
    if (isDrawTie(pair) && sw) {
      return '<span class="badge-close" title="The envelope median ranking disagrees with the central ranking. The ' +
        escapeHtml(threshold) + ' is 10 percent of draws.">Ranking is a tie: ' +
        escapeHtml(topPairTieClause(sw)) + "</span>";
    }
    var keep = pair.flip_share != null ? Math.max(1, Math.round((1 - pair.flip_share) * 5)) : 4;
    return '<span class="badge-close" title="The top two Handbook reforms are close enough that a different published assumption can swap them. The ' +
      escapeHtml(threshold) + ' is 10 percent of draws.">Ranking is close: ' +
      escapeHtml(scenarioLabel(pair.leader)) + " beat " + escapeHtml(scenarioLabel(pair.trailer)) +
      " in about " + keep + " of 5 test runs.</span>";
  }

  function answerLine() {
    var sw = docStatewide();
    var pair = sw.top_benchmark_pair;
    var pack = sw.results.package;
    var leader = (sw.benchmark_ranking || BENCHMARKS)[0];
    var leadRow = sw.results[leader];
    var adu = sw.results.adu;
    if (stateCode === "NH") {
      return "New Hampshire already allows ADUs statewide, so the ADU reform adds little there (" +
        signed(adu.central) + "). " + scenarioLabel(leader) + " still leads (" +
        signed(leadRow.central) + "). Same code, same assumptions, a second state.";
    }
    if (isDrawTie(pair)) {
      return "In " + locked.name + " over 2027–2031, " + topPairTieClause(sw) +
        ". All four reforms together add " + signed(pack.central) + " on top of " +
        integer(sw.results.baseline.central) + " expected.";
    }
    return "In " + locked.name + " over 2027–2031, " + scenarioLabel(leader) +
      " adds the most: about " + signed(leadRow.central) + " homes. All four reforms together add " +
      signed(pack.central) + " on top of " + integer(sw.results.baseline.central) + " expected.";
  }

  function renderHeadline() {
    var sw = docStatewide();
    var sid = activeScenario();
    var row = sw.results[sid] || sw.results.adu;
    var env = locked.statewide.results[sid] || locked.statewide.results.adu;
    var pair = sw.top_benchmark_pair;
    headline.innerHTML =
      '<p class="headline-answer">' + escapeHtml(answerLine()) + tag("calculated") + "</p>" +
      '<p class="help">' + rankingBadge(pair, sw) + " · " + escapeHtml(rankingLine(sw)) + "</p>" +
      '<p class="help">' + jargon("Envelope") + " " + integer(env.p10) + "–" + integer(env.p90) + tag("calculated") +
      " · " + jargon("Zoning") + " " + integer(row.zoning_low) + "–" + integer(row.zoning_high) + tag("calculated") +
      " · " + jargon("ACS MOE") + " ±" + integer(row.acs_moe) + tag("observed") + "</p>";
    document.getElementById("state-name").textContent = locked.name;
    var years = catalog ? catalog.window_start.slice(0, 4) + "–" +
      (Number(catalog.window_start.slice(0, 4)) + Number(catalog.horizon_years) - 1) : "2027–2031";
    document.getElementById("kicker").textContent = "Your package · " + years;
  }

  function anim(to) {
    var from = shown;
    var t0 = performance.now();
    var dur = RM ? 0 : 900;
    function step(t) {
      var p = dur ? Math.min(1, (t - t0) / dur) : 1;
      var e = 1 - Math.pow(1 - p, 3);
      shown = from + (to - from) * e;
      document.getElementById("count").textContent = "+" + integer(shown);
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function renderCount() {
    var t = packageTotal();
    var sw = docStatewide();
    var baseline = sw.results.baseline.central;
    anim(t.c);
    var mx = Math.max(sw.results.package.p90 * 1.05, 1);
    var band = document.getElementById("band");
    var tick = document.getElementById("tick");
    if (t.exact && t.c) {
      band.style.left = (t.lo / mx * 100) + "%";
      band.style.width = ((t.hi - t.lo) / mx * 100) + "%";
    } else {
      band.style.left = "0";
      band.style.width = "0";
    }
    tick.style.left = (t.c / mx * 100) + "%";
    var range = document.getElementById("rangeline");
    var liveEl = document.getElementById("count-live");
    if (!on.size) {
      range.textContent = "Turn on a reform below to start.";
      liveEl.textContent = "No reforms selected.";
    } else if (t.exact) {
      range.innerHTML = "Likely range <b>" + integer(t.lo) + " – " + integer(t.hi) +
        "</b> extra homes · on top of " + integer(baseline) + " expected anyway " + tag("calculated");
      liveEl.textContent = "Your package: about " + integer(t.c) + " extra homes, likely " +
        integer(t.lo) + " to " + integer(t.hi) + ".";
    } else {
      range.innerHTML = "<b>" + escapeHtml(HONESTY.charAt(0).toUpperCase() + HONESTY.slice(1)) + "</b> " +
        escapeHtml(HONESTY_LONG);
      liveEl.textContent = "Your package: about " + integer(t.c) + " extra homes, simple sum, not modeled.";
    }
    var relate = document.getElementById("relate");
    relate.textContent = on.size
      ? "That's about " + (t.c / baseline * 100).toFixed(1) + "% more homes than " +
        locked.name + " is expected to finish anyway over five years."
      : "";
  }

  function renderRecon() {
    var note = catalog && catalog.reconciliation_note;
    var box = document.getElementById("recon");
    var methods = document.getElementById("methods-recon");
    if (!note) {
      box.hidden = true;
      if (methods) methods.hidden = true;
      return;
    }
    box.hidden = false;
    box.textContent = note;
    if (methods) {
      methods.hidden = false;
      methods.textContent = note;
    }
  }

  function closeBadgeHtml(k, sw) {
    var pair = sw.top_benchmark_pair;
    if (!pair || !pair.close_call) return "";
    if (k !== pair.leader && k !== pair.trailer) return "";
    var flip = Math.round(pair.flip_share * 100);
    return '<button type="button" class="badge" aria-expanded="false" data-badge="close">Ranking is close</button>' +
      '<span class="sr">order flips in ' + flip + "% of test runs. Both are strong options.</span>";
  }

  function outcomeBadgeHtml(row) {
    if (!row || row.p10 > 0) return "";
    return '<button type="button" class="badge badge-out" aria-expanded="false" data-badge="out">Outcome uncertain</button>';
  }

  function renderCards() {
    var sw = docStatewide();
    var rank = rankedBenchmarks();
    var mx = sw.results.package.p90;
    cards.innerHTML = rank.map(function (k, i) {
      var row = sw.results[k];
      var pressed = on.has(k);
      return '<article class="card" role="listitem" aria-pressed="' + pressed + '">' +
        '<button type="button" class="tog" aria-pressed="' + pressed + '" data-k="' + k + '">' +
        "<span><span class='help'>#" + (i + 1) + " on its own</span><h3>" + escapeHtml(PLAIN[k]) +
        "</h3></span><span class='sw' aria-hidden='true'></span></button>" +
        '<div class="n">' + signed(row.central) + tag("calculated") + "</div>" +
        '<div class="mini" aria-hidden="true"><i style="left:' + (row.p10 / mx * 100) +
        "%;width:" + ((row.p90 - row.p10) / mx * 100) + '%"></i><b style="left:' +
        (row.central / mx * 100) + '%"></b></div>' +
        '<div class="r">Likely range ' + integer(row.p10) + "–" + integer(row.p90) + "</div>" +
        closeBadgeHtml(k, sw) + outcomeBadgeHtml(row) + "</article>";
    }).join("");
    extraCards.innerHTML = (locked.scenarios || []).filter(function (s) {
      return s.id === "approval";
    }).map(function (s) {
      var row = sw.results[s.id];
      return '<article class="scenario-card" data-sid="' + s.id + '"><div class="card-top"><h3><button type="button" data-sid="' +
        s.id + '">' + escapeHtml(cardTitle(s)) + "</button></h3><span class='pill t2'>extra</span></div>" +
        "<p class='plain'>" + signed(row.central) + " vs Baseline" + tag("calculated") +
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
          btn.textContent = open ? "Ranking is close" :
            "Ranking is close: order flips in " + Math.round(pair.flip_share * 100) +
            "% of test runs. Both are strong options.";
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
        COL[k] + '" title="' + escapeHtml(PLAIN[k]) + '"></span>';
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
      line.innerHTML = "Adding the cards: <b>" + integer(d.sum_of_separate) + "</b>. Modeled together: <b>" +
        integer(d.package) + "</b>." + tag("calculated");
      box.innerHTML = "<b>Don't add the bills up.</b> ADUs and 2–6 homes compete for the same lots (" +
        integer(Math.abs(d.competition_loss)) + " fewer homes than adding them), but a fee cut is worth more when paired with them (fee step " +
        signed(d.fee_cut_step) + ", parking step " + signed(d.parking_step) + "). Net: " +
        integer(d.package) + " vs " + integer(d.sum_of_separate) + " if added. Interaction " +
        signed(d.interaction) + ". Package is not a sum." + tag("calculated");
    } else {
      line.innerHTML = "Adding the cards: <b>" + integer(sum) + "</b>. " + escapeHtml(HONESTY);
      box.textContent = HONESTY_LONG + " The engine has been run for each reform alone and for all four together.";
    }
  }

  function renderChips() {
    var el = document.getElementById("chips");
    var ids = rankedBenchmarks();
    el.innerHTML = ids.map(function (k) {
      return '<button type="button" aria-pressed="' + on.has(k) + '" data-chip="' + k + '">' +
        escapeHtml(CHIP_LABEL[k]) + "</button>";
    }).join("") +
      '<button type="button" aria-pressed="' + (on.size === 4) + '" data-chip="all">All four</button>';
    el.querySelectorAll("[data-chip]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var k = btn.getAttribute("data-chip");
        if (k === "all") {
          if (on.size === 4) on = new Set([rankedBenchmarks()[0]]);
          else on = new Set(BENCHMARKS);
        } else if (on.has(k) && on.size === 1) {
          return;
        } else {
          on = new Set([k]);
          scenarioId = k;
        }
        renderAll();
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
      maxAbs = Math.max(maxAbs, Math.abs(countyPackageValue(c)));
    });
    var paths = geoDoc.counties.map(function (c) {
      var row = countyRow(c.fips);
      var value = row ? countyPackageValue(row) : 0;
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
    var value = countyPackageValue(row);
    var sid = ids.length === 1 ? ids[0] : ids.length === 4 ? "package" : null;
    var env = sid ? cell(row, sid) : null;
    var text = row.name + ": " + signed(value) + " extra homes" +
      (env ? " (likely " + integer(env.p10) + "–" + integer(env.p90) + ")" :
        ids.length ? " (simple sum; model run pending)" : "") +
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
    var sid = activeScenario();
    var current = cell(row, sid);
    var env = lockedCell(row.fips, sid) || current;
    var pair = row.top_benchmark_pair;
    var cover = row.coverage || {};
    countyDetail.hidden = false;
    countyDetail.innerHTML =
      "<p><strong>" + escapeHtml(row.name) + "</strong> — " +
      scenarioLabel(sid) + " " + signed(countyPackageValue(row)) + tag("calculated") +
      " (likely " + integer(env.p10) + "–" + integer(env.p90) + tag("assumed") +
      ") on top of " + integer(cell(row, "baseline").central) + " expected " + tag("calculated") +
      ". Eligible " + integer(current.eligible) + tag("calculated") +
      ", feasible " + integer(current.feasible) + tag("calculated") +
      ". " + jargon("Zoning") + " " + integer(current.zoning_low) + "–" + integer(current.zoning_high) + tag("calculated") +
      ". " + jargon("ACS MOE") + " ±" + integer(current.acs_moe) + tag("observed") +
      ". Local zoning known for " + pct(cover.adu || 0) + " of ADU lots " + tag("observed") +
      ". " + rankingBadge(pair) + ".</p>";
  }

  function renderTable() {
    var sid = activeScenario();
    var rows = docCounties().slice().sort(function (a, b) {
      return Math.abs(countyPackageValue(b)) - Math.abs(countyPackageValue(a));
    });
    countyBody.innerHTML = rows.map(function (row) {
      var current = cell(row, sid);
      var env = lockedCell(row.fips, sid) || current;
      return "<tr data-fips='" + row.fips + "' class='" + (row.fips === selectedFips ? "selected" : "") + "'>" +
        "<td>" + escapeHtml(row.name) + "</td>" +
        "<td>" + signed(countyPackageValue(row)) + "</td>" +
        "<td>" + integer(current.eligible) + "</td>" +
        "<td>" + integer(current.feasible) + "</td>" +
        "<td>" + integer(env.p10) + "–" + integer(env.p90) + "</td>" +
        "<td>" + integer(current.zoning_low) + "–" + integer(current.zoning_high) + "</td>" +
        "<td>±" + integer(current.acs_moe) + "</td></tr>";
    }).join("");
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
      return countyPackageValue(b) - countyPackageValue(a);
    }).slice(0, 15);
    var sid = activeScenario();
    var max = Math.max.apply(null, rows.map(function (r) {
      var env = lockedCell(r.fips, sid) || cell(r, sid);
      return Math.max(countyPackageValue(r), env.p90 || 0);
    }).concat([1]));
    var W = 720, rowH = 28, H = 40 + rows.length * rowH;
    var bars = rows.map(function (row, i) {
      var v = countyPackageValue(row);
      var env = lockedCell(row.fips, sid) || cell(row, sid);
      var y = 24 + i * rowH;
      var x0 = 180, usable = 500;
      var x = x0 + Math.max(0, v) / max * usable;
      var lo = x0 + Math.max(0, env.p10) / max * usable;
      var hi = x0 + Math.max(0, env.p90) / max * usable;
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
        tab.setAttribute("aria-selected", onTab ? "true" : "false");
      }
      if (panel && name !== "map") panel.hidden = !onTab;
    });
    if (!silent) writeUrl();
    if (view === "map" && !silent) {
      document.getElementById("map-stage").scrollIntoView({ behavior: RM ? "auto" : "smooth", block: "center" });
    }
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
      return "<details class='slider-group'><summary>" + escapeHtml(group) + "</summary>" + inner + "</details>";
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
      var t = packageTotal();
      setStatus("Updated: package now " + signed(t.c) + ". Live central / zoning / ACS. Envelope locked.");
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
    var sid = activeScenario();
    var payload = { state: stateCode, county: selectedFips, scenario: sid === "package" ? "package" : sid, overrides: overrides };
    post("/api/lab/why", payload).then(function (doc) {
      whyDoc = doc;
      renderWhy();
      renderKeyPoints();
      renderSources();
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
      (whyDoc.lots_note ? "<p class='help'>" + escapeHtml(whyDoc.lots_note) + "</p>" : "") +
      (whyDoc.imputed.length ? "<p class='help'>Imputed ACS fields, never zero: " + escapeHtml(whyDoc.imputed.join(", ")) + ".</p>" : "") +
      "<h3>Inputs</h3><div class='receipt'>" + inputs + "</div>" +
      "<h3>Assumptions used</h3><div class='receipt'>" + assumptions + "</div>" +
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
    var head = document.getElementById("why-heading");
    if (head) head.focus();
  }

  function renderKeyPoints() {
    var list = document.getElementById("keypoints-list");
    if (!list || !locked) return;
    var sid = activeScenario();
    var row = selectedFips ? countyRow(selectedFips) : null;
    var current = row ? cell(row, sid) : docStatewide().results[sid];
    var eligible = current.eligible;
    var feasible = current.feasible;
    var ratio = eligible ? feasible / eligible : 0;
    var wwc = locked.statewide.what_would_change;
    var switch0 = wwc && wwc.switches && wwc.switches[0];
    var bullets = [
      "Most of the gain comes from converting existing homes, not teardowns. Host term " +
        signed((row ? cell(row, sid) : docStatewide().results[sid]).host_delta) + ".",
      eligible ? ("Fewer than " + (ratio > 0 ? "1 in " + Math.max(1, Math.round(1 / ratio)) : "all") +
        " lots where it becomes legal also pencil out (" + integer(feasible) + " of " + integer(eligible) + ").") :
        "Eligible and feasible counts come from the locked county run.",
      switch0 ? ("The result is most sensitive to " + switch0.label.toLowerCase() +
        ". Order can flip at " + formatParam({ unit: switch0.unit }, switch0.switch_at) + ".") :
        "The ranking can move when a published assumption changes."
    ];
    list.innerHTML = bullets.map(function (b) { return "<li>" + escapeHtml(b) + " " + tag("calculated") + "</li>"; }).join("");
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
      "<li>ADU evidence coverage " + pct(cover.adu) + " · 2–6-home evidence " + pct(cover.mm) + " " + tag("calculated") + "</li>" +
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
        var first = block.adu || block.missing_middle || {};
        var err = first.imputed_parcels && first.imputed_parcels.percent_error;
        return code + (err == null ? "" : " " + (err > 0 ? "+" : "") + err.toFixed(1) + "%");
      });
      el.innerHTML = "Error vs. parcel data on the states that have extracts: " +
        escapeHtml(parts.join(" · ") || "see Cross-check on the screening view") +
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
    var rows = rank.map(function (k) {
      var r = sw.results[k];
      return "<tr><td>" + escapeHtml(PLAIN[k]) + "</td><td>" + signed(r.central) +
        "</td><td>" + integer(r.p10) + "–" + integer(r.p90) + "</td></tr>";
    }).join("");
    var d = sw.package_decomposition;
    el.innerHTML =
      "<h1>" + escapeHtml(answerLine()) + "</h1>" +
      "<p>Bottom line: the selected package is " + signed(t.c) +
      (t.exact ? " (likely " + integer(t.lo) + "–" + integer(t.hi) + ")" : " — " + HONESTY) +
      " on top of " + integer(sw.results.baseline.central) + " expected.</p>" +
      "<table><thead><tr><th>Reform</th><th>Extra homes</th><th>Likely range</th></tr></thead><tbody>" +
      rows +
      "<tr><td>All four together (don't add the bills up)</td><td>" + signed(d.package) +
      "</td><td>" + integer(sw.results.package.p10) + "–" + integer(sw.results.package.p90) +
      "</td></tr></tbody></table>" +
      "<p>" + escapeHtml(rankingLine(sw)) + ". " +
      (sw.top_benchmark_pair.close_call ? "Ranking is close." : "Ranking holds.") + "</p>" +
      "<p>Also modeled, not a Handbook benchmark: by-right approval with a shot clock, " +
      signed(sw.results.approval.central) + ".</p>" +
      "<p>Key assumptions: homeowner uptake, conversion cost, and ADU fees stay inside the published bands.</p>" +
      "<p>What this cannot tell you: it is not a forecast of which lots will build, and it is not a backtest against homes already built.</p>" +
      (catalog && catalog.reconciliation_note ? "<p>" + escapeHtml(catalog.reconciliation_note) + "</p>" : "") +
      "<p>" + location.href.split("#")[0] + " · " + locked.generated + "</p>";
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
    selectedFips = "42003";
    view = "map";
    writeUrl();
    var go = function () {
      renderAll();
      var target = document.getElementById("package");
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
    var sid = activeScenario();
    var header = ["county", "fips", "extra_homes", "eligible", "feasible", "p10", "p90", "zoning_low", "zoning_high", "acs_moe"];
    var lines = [header.join(",")];
    docCounties().forEach(function (row) {
      var current = cell(row, sid);
      var env = lockedCell(row.fips, sid) || current;
      lines.push([
        '"' + row.name.replace(/"/g, '""') + '"',
        row.fips,
        Math.round(countyPackageValue(row)),
        Math.round(current.eligible),
        Math.round(current.feasible),
        Math.round(env.p10),
        Math.round(env.p90),
        Math.round(current.zoning_low),
        Math.round(current.zoning_high),
        Math.round(current.acs_moe)
      ].join(","));
    });
    downloadBlob(new Blob([lines.join("\n")], { type: "text/csv" }), "stateframe-" + stateCode + "-counties.csv");
  }

  function printBrief() {
    renderBrief();
    window.print();
  }

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
      downloadBlob(file.blob, file.name);
    }).catch(function (err) { setStatus(err.message); });
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

  whyToggle.addEventListener("click", function () {
    setWhy(!whyOpen);
  });
  document.getElementById("why-close").addEventListener("click", function () {
    setWhy(false);
  });
  document.getElementById("why-adjust").addEventListener("click", function () {
    document.getElementById("adjust").scrollIntoView({ behavior: RM ? "auto" : "smooth" });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
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
    envelopeNote.textContent = "Move one slider. Central values, zoning bounds, and the ACS band recompute. The p10–p90 envelope stays on the locked " + ((locked && locked.draws) ? Number(locked.draws).toLocaleString("en-US") : "2,000") + "-draw run.";
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
    document.getElementById("tab-" + name).addEventListener("click", function () { setView(name); });
  });

  parseUrl();
  var q = new URLSearchParams(location.search);
  var shouldTry = q.get("try") === "1";
  loadAll().then(function () {
    if (shouldTry) tryPennsylvania();
    loadChecked();
    var seen = false;
    try { seen = localStorage.getItem(TOUR_KEY) === "1"; } catch (err) {}
    if (!seen && location.hash.indexOf("notour") < 0) {
      setTimeout(function () {
        lastFocus = document.getElementById("tour-btn");
        showTour(0);
      }, RM ? 0 : 1200);
    }
  });
})();
