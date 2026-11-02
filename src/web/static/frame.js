/* Range-first headline, delivery funnel, driver table, limits, and brief copy.
   Every model number is passed in by the caller and marked data-bind. */
(function (root) {
  "use strict";

  var Fmt = root.StateframeFmt;
  if (!Fmt) throw new Error("Load fmt.js before frame.js");

  var esc = Fmt.esc;
  var homes = Fmt.homes;
  var signed = Fmt.signedHomes;
  var bind = Fmt.bind;

  var PLAIN = {
    adoption_lag_years: "Adoption and rulemaking lag",
    build_lag_adu_years: "ADU permit-to-completion",
    build_lag_conversion_years: "Conversion / addition permit-to-completion",
    build_lag_newbuild_years: "Small multifamily permit-to-completion",
    pipeline_response_lag_years: "Pipeline response lag",
    hazard_homeowner: "Share of homeowners who add an ADU each year (all lots)",
    hazard_homeowner_feasible: "Share of homeowners who add an ADU each year (lots where it pays off)",
    hazard_developer: "Share of profitable lots rebuilt with 2–6 homes each year",
    host_margin_sigma: "How much profit varies from lot to lot",
    hurdle_owner: "Minimum profit a homeowner needs to build",
    hurdle_developer: "Minimum profit a builder needs",
    cap_rate: "Rent-to-value return (cap rate)",
    opex_share: "Operating cost share",
    new_unit_rent_premium: "New-home rent premium over ACS median",
    adu_sqft: "ADU size",
    adu_cost_psf: "ADU hard cost",
    conversion_cost_per_unit: "Conversion / addition hard cost per added home",
    newbuild_cost_psf: "Small multifamily hard cost",
    soft_cost_share: "Soft costs",
    teardown_value_factor: "Teardown lot price vs typical home value",
    stall_cost_surface: "Surface space cost",
    parking_market_urban: "Parking builders still provide when not required — cities and towns",
    parking_market_suburban: "Parking builders still provide when not required — suburbs",
    parking_market_rural: "Parking builders still provide when not required — rural areas",
    parking_sf_gap_share: "Share of single-family parking rules builders would skip",
    parking_constrained_share_urban: "Urban multifamily sites where parking caps units",
    parking_min_urban: "Current minimum (urban areas)",
    parking_min_suburban: "Current minimum (suburban areas)",
    parking_min_rural: "Current minimum (rural areas)",
    prior_adu_prohibited: "Chance ADUs are banned where local rules are unknown",
    prior_adu_prohibited_nh_attached: "NH attached-host ADU prohibited (townhouse exception)",
    prior_mm_prohibited: "Chance 2–6 homes are banned where local rules are unknown",
    pipeline_sigma: "How much profit varies between projects",
    permit_trend: "Baseline permit trend",
    approval_time_saved_years: "Approval time saved",
    approval_discretionary_share: "Pipeline homes that go through discretionary review today",
    adu_feasible_share_ca: "California feasible-lot share",
    nh_detached_adu_already_legal: "NH detached ADUs already legal before 2025"
  };

  var GROUPS = {
    timing: "Timing: how long things take",
    uptake: "Uptake: how many people build",
    feasibility: "Does it pay off?",
    costs: "Building costs and fees",
    parking: "Parking",
    lots: "Lot sizes and room to build",
    zoning: "Unknown local rules",
    pipeline: "Projects already in the pipeline",
    approval: "Permit approval time"
  };

  var NOT_MODELLED = "Not modelled for this reform: this reform changes costs for projects, not what is legal.";
  var FUNNEL_UNAVAILABLE = "Funnel not available in the screening model: it estimates the effect directly from state-level response rates.";
  var NOT_FORECAST = "an estimate";
  var CHANGE_NOTE = "The Change column is the difference the reform makes at each step. It can look out of order, because lots that were already legal can switch to a better-paying option. The bars show the full totals with and without the reform, which always narrow step by step.";
  var NEGATIVE_TIP = "Fewer lots take this path because a better option replaced it.";
  var MIDDLE_TIP = "The result with every assumption at its middle value. The range comes from the test runs that vary the assumptions.";
  var PARKING_SOURCE = "Based on Buffalo after it dropped parking minimums (Hess & Rehler 2021): projects kept building about 1 space per home.";

  var SCENARIO_PLAIN = {
    missing_middle: {
      hazard_homeowner: "Share of owners who add 2–6 homes each year",
      hazard_homeowner_feasible: "Share of owners who add 2–6 homes each year on lots where it pays off",
      hazard_developer: "Share of profitable lots rebuilt with 2–6 homes each year"
    }
  };

  function plainLabel(key, fallback, sid) {
    var scoped = sid && SCENARIO_PLAIN[sid] && SCENARIO_PLAIN[sid][key];
    return scoped || PLAIN[key] || fallback || key;
  }

  function groupHeading(key) {
    return GROUPS[key] || key;
  }

  function rangeSpans(lowPath, highPath, low, high) {
    var a = Number(low);
    var b = Number(high);
    if (!isFinite(a) || !isFinite(b)) return "Likely range unavailable";
    var joiner = a <= 0 || b <= 0 ? " to " : "–";
    return bind(lowPath, homes(a)) + joiner + bind(highPath, homes(b));
  }

  function pctOf(middle, baseline) {
    var m = Number(middle);
    var b = Number(baseline);
    if (!isFinite(m) || !isFinite(b) || b === 0) return null;
    return m / b;
  }

  function knownNumber(value) {
    return value !== null && value !== undefined && value !== "" && isFinite(Number(value));
  }

  function derived(name, text, sources) {
    var from = sources ? ' data-from="' + esc(sources) + '"' : "";
    return '<span data-derived="' + esc(name) + '"' + from + ">" + text + "</span>";
  }

  function headlineParts(opts) {
    opts = opts || {};
    var paths = opts.paths || {};
    if (opts.unmodeled) {
      return {
        rangeHtml: "",
        middleHtml: "",
        html: "<p class=\"range-hero\">Not computed for this combination. Pick one reform, or all four, for a modeled total.</p>",
        live: ""
      };
    }
    var empty = !opts.sid;
    if (empty) {
      var emptyHtml = "<p>Pick a reform to see the extra homes.</p>";
      return {
        rangeHtml: "",
        middleHtml: "",
        html: emptyHtml,
        live: ""
      };
    }
    var reference = opts.status === "reference";
    var unavailable = opts.status === "unavailable" || !knownNumber(opts.low) || !knownNumber(opts.high);
    var kicker = reference
      ? "Reference range — from default assumptions, not recomputed"
      : "Likely range (10th–90th percentile, model-conditional)";
    var rangeInner = unavailable ? "Likely range unavailable" : rangeSpans(paths.low, paths.high, opts.low, opts.high);
    var lead = reference
      ? "Reference range " + rangeInner + ", from default settings, not recomputed"
      : "Likely " + rangeInner + " extra homes";
    var middle = bind(paths.middle, signed(opts.middle));
    var share = pctOf(opts.middle, opts.baseline);
    var pctText = share == null ? "No data" : (share * 100).toFixed(1) + "%";
    var draws = opts.draws == null ? "" : String(opts.draws);
    var html = '<p class="range-kicker">' + esc(kicker) + "</p>" +
      '<p class="range-hero">' + lead + "</p>" +
      '<p class="middle-est">Middle estimate ' + middle + ". " +
      Fmt.tipButton("What middle estimate means", MIDDLE_TIP + (draws ? " Runs: " + draws + "." : "")) +
      "</p>" +
      "<p class=\"baseline-line\">By " + bind(paths.endYear, esc(opts.endYear || "")) +
      " in " + esc(opts.stateName || "") +
      " under the stated assumptions. That is on top of " +
      bind(paths.baseline, homes(opts.baseline)) +
      " expected without these reforms (" +
      bind("derived.lift." + (opts.sid || ""), pctText) +
      " more).</p>";
    var live = (reference ? "Reference range, not recomputed. " : "Likely range. ") +
      (unavailable ? "Likely range unavailable. " : Fmt.rangeText(opts.low, opts.high) + " extra homes. ") +
      "Middle estimate " + signed(opts.middle) + ".";
    return {
      rangeHtml: unavailable ? "Likely range unavailable" : rangeSpans(paths.low, paths.high, opts.low, opts.high),
      middleHtml: "Middle estimate " + middle,
      html: html,
      live: live
    };
  }

  function miniTotal(opts) {
    opts = opts || {};
    if (opts.unmodeled) {
      return esc(opts.label || "Your package") +
        ' · <span class="model-badge county">County model</span>';
    }
    if (!opts.sid) return "";
    var paths = opts.paths || {};
    var rangeWord = opts.status === "reference" ? "Reference range, not recomputed, " : "likely ";
    var range = knownNumber(opts.low) && knownNumber(opts.high)
      ? rangeSpans(paths.low, paths.high, opts.low, opts.high)
      : "Likely range unavailable";
    return esc(opts.label || "Package") + ": " + rangeWord + range +
      " extra homes · middle " + bind(paths.middle, signed(opts.middle)) +
      " · <span class=\"model-badge county\">County model</span>";
  }

  function numOrNull(value) {
    if (value === null || value === undefined || value === "") return null;
    var n = Number(value);
    return isFinite(n) ? n : null;
  }

  function lotSpan(path, value) {
    var n = numOrNull(value);
    if (n === null) return "No data";
    return bind(path, homes(n)) + " lots";
  }

  function homeSpan(path, value) {
    var n = numOrNull(value);
    if (n === null) return "No data";
    return bind(path, signed(n)) + " homes";
  }

  function shareText(value) {
    var n = numOrNull(value);
    if (n === null) return null;
    return (n * 100).toFixed(1) + "%";
  }

  function funnelHtml(opts) {
    opts = opts || {};
    var sid = opts.sid || "";
    if (opts.screening) {
      return '<section class="funnel" data-funnel="unavailable"><p>' + esc(FUNNEL_UNAVAILABLE) + "</p></section>";
    }
    if (sid === "parking" || sid === "fees" || opts.funnel === null) {
      var fees = "";
      if (sid === "fees" && Math.abs(Number(opts.feesLotHomes) || 0) >= 1) {
        fees = "<p class=\"fees-lot-note\">The total includes " +
          homeSpan(opts.feesPath || "statewide.results.fees.host_delta", opts.feesLotHomes) +
          " from lots (fees make a few more home additions pay). Lot-level detail isn't broken out for this reform.</p>";
      }
      return '<section class="funnel" data-funnel="skipped"><p>' + esc(NOT_MODELLED) + "</p>" + fees + "</section>";
    }
    var funnel = opts.funnel;
    if (!funnel) {
      return '<section class="funnel" data-funnel="empty"><p>Turn on one reform to see how many legal lots become built homes.</p></section>';
    }
    var prefix = opts.prefix || ("statewide.results." + sid + ".funnel");
    var gross = funnel.gross || {};
    var base = funnel.baseline_gross || {};
    var endYear = opts.endYear || "";
    var stages = [
      ["legal_fits", "Lots where a legal option fits", "lots"],
      ["pays", "Lots where the best option would pay for itself", "lots"],
      ["go_ahead", "Lots where the owner starts within the window", "lots"],
      ["finishing", "Lots that start in time to finish by " + endYear, "lots"],
      ["delivered", "Extra homes from lots (result)", "homes"]
    ];
    var maxGross = 1;
    stages.forEach(function (stage) {
      maxGross = Math.max(maxGross, Number(gross[stage[0]]) || 0, Number(base[stage[0]]) || 0);
    });
    function bar(kind, value) {
      var n = numOrNull(value);
      var width = n === null || n <= 0 ? 0 : (Math.log10(n + 1) / Math.log10(maxGross + 1) * 100);
      return '<span class="funnel-bar ' + kind + '" style="width:' + width.toFixed(1) +
        '%" aria-hidden="true"></span>';
    }
    function changeCell(name, unit) {
      var value = funnel[name];
      var path = prefix + "." + name;
      if (numOrNull(value) === null) return "No data";
      var text = unit === "homes" ? homeSpan(path, value) : (bind(path, signed(value)) + " lots");
      if (Number(value) < 0) text += " " + Fmt.tipButton("Fewer", NEGATIVE_TIP);
      return text;
    }
    var rows = stages.map(function (stage, index) {
      var name = stage[0];
      var unit = stage[2];
      var withText = unit === "homes"
        ? homeSpan(prefix + ".gross." + name, gross[name])
        : lotSpan(prefix + ".gross." + name, gross[name]);
      var withoutText = unit === "homes"
        ? homeSpan(prefix + ".baseline_gross." + name, base[name])
        : lotSpan(prefix + ".baseline_gross." + name, base[name]);
      var tag = index < 4 ? ' <span class="tag-note">' + NOT_FORECAST + "</span>" : "";
      return "<tr class=\"" + (index < 4 ? "lot-step" : "funnel-result") + "\">" +
        "<th scope=\"row\">" + esc(stage[1]) + tag + "</th>" +
        "<td>" + bar("with", gross[name]) +
        '<span class="funnel-text">with ' + withText + "</span></td>" +
        "<td>" + bar("without", base[name]) +
        '<span class="funnel-text">without ' + withoutText + "</span></td>" +
        "<td>" + changeCell(name, unit) + "</td></tr>";
    }).join("");
    function ratioLine(text) {
      return text ? "<p class=\"funnel-ratio\">" + text + "</p>" : "";
    }
    var legal = numOrNull(gross.legal_fits);
    var pays = numOrNull(gross.pays);
    var go = numOrNull(gross.go_ahead);
    var finishing = numOrNull(gross.finishing);
    var payShare = legal != null && legal >= 1 && pays != null ? pays / legal : null;
    var goShare = numOrNull(gross.go_ahead_share);
    if (goShare == null && pays != null && pays >= 1 && go != null) goShare = go / pays;
    if (pays != null && pays < 1) goShare = null;
    var timing = numOrNull(gross.timing);
    if (timing == null && go != null && go >= 1 && finishing != null) timing = finishing / go;
    if (go != null && go < 1) timing = null;
    var ratios = ratioLine(payShare == null ? "" :
      derived("pays/legal_fits", shareText(payShare), prefix + ".gross.pays " + prefix + ".gross.legal_fits") +
      " of legal lots would pay (" + lotSpan(prefix + ".gross.pays", gross.pays) +
      " of " + lotSpan(prefix + ".gross.legal_fits", gross.legal_fits) + ").") +
      ratioLine(goShare == null ? "" :
        bind(prefix + ".gross.go_ahead_share", shareText(goShare)) +
        " of lots whose project pays go ahead (" +
        lotSpan(prefix + ".gross.go_ahead", gross.go_ahead) + ").") +
      ratioLine(timing == null ? "" :
        bind(prefix + ".gross.timing", shareText(timing)) +
        " of started lots start early enough to finish by " + esc(endYear) +
        " (" + lotSpan(prefix + ".gross.finishing", gross.finishing) + ").");
    var completion = numOrNull(funnel.completion);
    var completionLine = "";
    if (completion != null && Math.abs(completion - 1) < 1e-9) {
      completionLine = "<p>All started projects finish within the model (completion " +
        bind(prefix + ".completion", shareText(completion)) + ").</p>";
    } else if (completion != null) {
      completionLine = "<p>" + bind(prefix + ".completion", shareText(completion)) +
        " of started projects finish.</p>";
    }
    var perLot = numOrNull(funnel.homes_per_lot);
    var perLotLine = perLot == null ? "" :
      "<p>" + bind(prefix + ".homes_per_lot", perLot.toFixed(2)) + " homes per lot.</p>";
    var other = numOrNull(funnel.other_channels);
    var otherRow = "";
    if (other != null && Math.abs(other) >= 0.5) {
      otherRow = "<tr><th scope=\"row\">Other channels: projects already planned and faster approvals</th>" +
        "<td colspan=\"2\">—</td><td>" + homeSpan(prefix + ".other_channels", other) + "</td></tr>";
    }
    var totalRow = "<tr class=\"funnel-total\"><th scope=\"row\">Extra homes by " + esc(endYear) + "</th>" +
      "<td colspan=\"2\"></td><td><strong>" + homeSpan(opts.middlePath || ("statewide.results." + sid + ".central"), opts.middle) +
      "</strong>, likely " + rangeSpans(opts.lowPath, opts.highPath, opts.low, opts.high) + " homes</td></tr>";
    var caption = "From legal to built: " + (opts.stateName || "") + ", " + (opts.label || sid) +
      ". Steps 1–4 in lots; result, other channels and total in homes; with and without the reform";
    var scopeNote = funnel.scope === "package_combined_lots"
      ? "<p>Package: all lots combined; the reforms can't be separated lot by lot.</p>"
      : "";
    var open = opts.collapseSteps ? "" : " open";
    return '<section class="funnel" data-funnel="shown">' +
      "<h3>How we got here</h3>" + scopeNote +
      '<p class="help">Bar lengths use a log scale. ' + esc(CHANGE_NOTE) + "</p>" +
      "<details class=\"lot-steps\"" + open + "><summary>Show the lot steps (estimates)</summary>" +
      ratios + completionLine + perLotLine + "</details>" +
      '<div class="table-region" role="region" tabindex="0" aria-label="Delivery funnel for ' +
      esc(opts.label || sid) + ', scrolls sideways">' +
      "<table class=\"funnel-table\"><caption>" + esc(caption) + "</caption>" +
      "<thead><tr><th scope=\"col\">Stage</th><th scope=\"col\">With the reform</th>" +
      "<th scope=\"col\">Without it</th><th scope=\"col\">Change</th></tr></thead><tbody>" +
      rows + otherRow + totalRow + "</tbody></table></div></section>";
  }

  function rankDrivers(oat, sid, params) {
    var rows = [];
    (params || []).forEach(function (spec, index) {
      var ends = oat && oat[spec.name];
      if (!ends || !ends.low || !ends.high) return;
      var low = Number(ends.low[sid]);
      var high = Number(ends.high[sid]);
      if (!isFinite(low) || !isFinite(high)) return;
      rows.push({
        key: spec.name,
        label: plainLabel(spec.name, spec.label, sid),
        low: low,
        high: high,
        swing: Math.abs(high - low),
        bandLow: spec.low,
        bandHigh: spec.high,
        unit: spec.unit || "",
        tag: spec.tag || "assumed",
        order: index
      });
    });
    rows.sort(function (a, b) {
      if (b.swing !== a.swing) return b.swing - a.swing;
      return a.order - b.order;
    });
    return rows;
  }

  function bandText(spec, formatBand) {
    if (typeof formatBand === "function") return formatBand(spec, spec.low) + "–" + formatBand(spec, spec.high);
    return String(spec.low) + "–" + String(spec.high);
  }

  function driversHtml(opts) {
    opts = opts || {};
    var sid = opts.sid;
    if (!sid) {
      return '<section id="driver-table" class="drivers"><h2>Assumptions that matter most</h2>' +
        "<p>Pick one reform, or all four, to rank assumptions for that result.</p></section>";
    }
    var ranked = rankDrivers(opts.oat, sid, opts.params);
    var shown = opts.showAll ? ranked : ranked.slice(0, 5);
    var prefix = "statewide.one_at_a_time.";
    var body = shown.map(function (row, index) {
      var changed = opts.changed && Object.prototype.hasOwnProperty.call(opts.changed, row.key);
      return "<tr" + (changed ? ' class="driver-changed"' : "") + ">" +
        "<td>" + (index + 1) + "</td>" +
        "<th scope=\"row\">" + esc(row.label) + (changed ? " <span class=\"you-changed\">you changed this</span>" : "") + "</th>" +
        "<td>" + (opts.formatFigure
          ? bind("by_name." + row.key + ".low", opts.formatFigure(row.unit, row.bandLow)) + "–" +
            bind("by_name." + row.key + ".high", opts.formatFigure(row.unit, row.bandHigh))
          : esc(row.bandLow + "–" + row.bandHigh)) + "</td>" +
        "<td>" + bind(prefix + row.key + ".low." + sid, signed(row.low)) + "</td>" +
        "<td>" + bind(prefix + row.key + ".high." + sid, signed(row.high)) + "</td>" +
        "<td>" + bind("derived.swing." + row.key + "." + sid, homes(row.swing)) + " homes</td>" +
        "<td>" + esc(row.tag) + "</td>" +
        '<td><button type="button" class="driver-adjust" data-driver="' + esc(row.key) + '">Adjust</button></td></tr>';
    }).join("");
    var more = ranked.length > 5
      ? '<button type="button" id="drivers-more" aria-expanded="' + (opts.showAll ? "true" : "false") + '">' +
        (opts.showAll ? "Show top 5" : "Show all " + ranked.length) + "</button>"
      : "";
    var overrideNote = opts.hasOverrides ? "<p>Your changes are not reflected in this ranking.</p>" : "";
    var switches = (opts.switches || []).map(function (row, index) {
      var way = row.direction === "low" ? "below" : "above";
      var at = opts.formatFigure ? opts.formatFigure(row.unit, row.switch_at) : String(row.switch_at);
      var base = "statewide.what_would_change.switches." + index + ".";
      var band = "";
      if (row.band) {
        var lo = opts.formatFigure ? opts.formatFigure(row.unit, row.band[0]) : String(row.band[0]);
        var hi = opts.formatFigure ? opts.formatFigure(row.unit, row.band[1]) : String(row.band[1]);
        band = " (tested range " + bind(base + "band.0", lo) + "–" + bind(base + "band.1", hi) + ")";
      }
      return "<li>" + esc(plainLabel(row.param, row.label, sid)) + " would have to be " + way + " " +
        bind(base + "switch_at", at) + band + ".</li>";
    }).join("");
    return '<section id="driver-table" class="drivers" aria-labelledby="drivers-title">' +
      '<h2 id="drivers-title">Assumptions that matter most</h2>' +
      '<p class="drivers-caption">Ranked at default settings. ' + esc(opts.label || "") + ".</p>" +
      overrideNote + more +
      '<div class="table-region" role="region" tabindex="0" aria-label="Assumptions that matter most, scrolls sideways">' +
      '<table><caption>Ranked at default settings</caption><thead><tr>' +
      "<th scope=\"col\">Rank</th><th scope=\"col\">Assumption</th><th scope=\"col\">Tested from–to</th>" +
      "<th scope=\"col\">Result at low end</th><th scope=\"col\">Result at high end</th>" +
      "<th scope=\"col\">How far the answer moves</th><th scope=\"col\">Source</th><th scope=\"col\">Adjust</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      (switches ? '<h3>What would change the ranking</h3><ul class="switch-list">' + switches + "</ul>" : "") +
      "</section>";
  }

  function parkingHtml(opts) {
    opts = opts || {};
    if (!opts.show) return "";
    var urban = bind(opts.urbanPath || "by_name.parking_market_urban.central", opts.urbanText || "");
    var rule = bind(opts.minPath || "anchors.parking_min_urban", opts.minText || "");
    return '<p class="parking-line">Assumes builders still provide about ' + urban +
      " spaces per home in cities (old rule: " + rule +
      ") even when not required.</p><p class=\"parking-source\">" + esc(PARKING_SOURCE) + "</p>";
  }

  function completionPair(ratios) {
    var adu = ratios && ratios.completion_ratio_adu && Number(ratios.completion_ratio_adu.central);
    var small = ratios && ratios.completion_ratio_small && Number(ratios.completion_ratio_small.central);
    if (!isFinite(adu) || !isFinite(small)) return null;
    var low = Math.min(adu, small);
    var high = Math.max(adu, small);
    var lowName = adu <= small ? "completion_ratio_adu" : "completion_ratio_small";
    var highName = adu <= small ? "completion_ratio_small" : "completion_ratio_adu";
    return { low: low, high: high, lowName: lowName, highName: highName };
  }

  function modelDiffHtml(ratios) {
    var pair = completionPair(ratios);
    var tail = " This is a known difference under review.";
    var lead = "The county model assumes started projects finish; the 11-state screening model applies a completion ratio";
    if (!pair) {
      return '<p class="model-diff" role="note" data-component="ModelDiffNote">' + lead + "." + tail + "</p>";
    }
    return '<p class="model-diff" role="note" data-component="ModelDiffNote">' + lead + " (" +
      bind("completion_ratios." + pair.lowName + ".central", pair.low.toFixed(2)) + "–" +
      bind("completion_ratios." + pair.highName + ".central", pair.high.toFixed(2)) +
      ")." + tail + "</p>";
  }

  function limitsHtml(opts) {
    opts = opts || {};
    var sid = opts.sid;
    var blocks = [];
    function push(title, items) {
      blocks.push("<section class=\"limits\" data-limits=\"" + esc(sid || "none") + "\"><h3>" +
        esc(title) + "</h3><ul>" + items.map(function (item) {
          return "<li>" + item + "</li>";
        }).join("") + "</ul>" + modelDiffHtml(opts.ratios) + "</section>");
    }
    var top = (opts.drivers || [])[0];
    var aduItems = [
      "It can't tell you which streets or owners will build, only county and state totals.",
      "The yearly build rate comes from California after its ADU laws. Other states may move faster or slower.",
      "It doesn't count apartments built without permits, and many states don't track them at all.",
      "It doesn't say whether units become rentals, family housing, or short-term rentals."
    ];
    var mmItems = [
      top ? ("How many owners actually build is the biggest unknown. At default settings, changing \"" +
        esc(top.label) + "\" alone moves the answer by about " +
        bind("derived.swing." + top.key + "." + (opts.driverSid || sid), homes(top.swing)) +
        " homes (" + bind("statewide.one_at_a_time." + top.key + ".low." + (opts.driverSid || sid), signed(top.low)) +
        " to " + bind("statewide.one_at_a_time." + top.key + ".high." + (opts.driverSid || sid), signed(top.high)) + ").")
        : "How many owners actually build is the biggest unknown.",
      "It assumes local rules on lot size, height, and setbacks stay as coded. Town rewrites can undo the law.",
      "It doesn't model neighborhood opposition, lawsuits, or lender reluctance."
    ];
    var parkItems = [
      "Builders often keep building parking anyway. We assume about " +
        bind(opts.parkingPath || "by_name.parking_market_urban.central", opts.parkingText || "") +
        " spaces per home in cities, and how far that moves the answer is shown in What matters most.",
      "It doesn't estimate effects on traffic, street parking, or transit use.",
      "The likely range is " + rangeSpans(opts.lowPath, opts.highPath, opts.low, opts.high) + " homes."
    ];
    if (isFinite(Number(opts.high)) && isFinite(Number(opts.baseline)) && Number(opts.baseline) > 0 &&
        Number(opts.high) < 0.01 * Number(opts.baseline)) {
      parkItems.push("The effect is small relative to normal building.");
    }
    var feeItems = [
      "It doesn't say how towns would replace lost fee money.",
      "It assumes savings reach the project budget, and doesn't model who captures them."
    ];
    var common = [
      "These are estimates under stated assumptions, not predictions.",
      "They leave out recessions, interest rates outside the tested band, and labor shortages.",
      "They say nothing about prices, rents, or who gets the homes."
    ];
    if (sid === "adu") push("What this can't tell you", aduItems.concat(common));
    else if (sid === "missing_middle") push("What this can't tell you", mmItems.concat(common));
    else if (sid === "parking") push("What this can't tell you", parkItems.concat(common));
    else if (sid === "fees") push("What this can't tell you", feeItems.concat(common));
    else if (sid === "package") {
      push("What this can't tell you", [
        "Modelled together, not added up: pieces can overlap on the same lot.",
        "It leaves out faster approvals and transit-area upzoning, which are not in the county model."
      ].concat(aduItems, mmItems, parkItems, feeItems, common));
    } else {
      push("What this can't tell you", common);
    }
    return blocks.join("");
  }

  function briefAnswer(opts) {
    opts = opts || {};
    if (!opts.sid && !opts.screeningMiddle) {
      return "<p>Pick at least one change to see a number.</p>";
    }
    if (opts.screening) {
      return '<p class="model-badge screening">Rough estimate (screening model)</p>' +
        '<p class="range-hero">Likely range unavailable</p>' +
        "<p>" + esc(FUNNEL_UNAVAILABLE) + "</p>" +
        '<p class="middle-est">Middle estimate ' +
        bind("scenarios.combined.incremental_completions", signed(opts.screeningMiddle)) +
        " extra homes by " + esc(opts.endYear || "") + " in " + esc(opts.stateName || "") + ".</p>";
    }
    var parts = headlineParts(opts);
    return '<p class="model-badge county">County model · county by county · PA, NH</p>' + parts.html;
  }

  function driverSentences(drivers, sid) {
    return (drivers || []).slice(0, 3).map(function (row) {
      var higher = row.high >= row.low;
      var reach = higher ? row.high : row.low;
      var way = higher ? "higher" : "lower";
      var path = "statewide.one_at_a_time." + row.key + "." + (higher ? "high." : "low.") + (sid || row.sid || "");
      return "<li>If " + esc(row.label) + " is " + way +
        " than we assume, the number could reach about " + bind(path, signed(reach)) + ".</li>";
    }).join("");
  }

  root.StateframeFrame = {
    plainLabel: plainLabel,
    groupHeading: groupHeading,
    headlineParts: headlineParts,
    miniTotal: miniTotal,
    funnelHtml: funnelHtml,
    rankDrivers: rankDrivers,
    driversHtml: driversHtml,
    parkingHtml: parkingHtml,
    modelDiffHtml: modelDiffHtml,
    limitsHtml: limitsHtml,
    briefAnswer: briefAnswer,
    driverSentences: driverSentences,
    completionPair: completionPair,
    rangeSpans: rangeSpans,
    NOT_MODELLED: NOT_MODELLED,
    FUNNEL_UNAVAILABLE: FUNNEL_UNAVAILABLE,
    NOT_FORECAST: NOT_FORECAST,
    PARKING_SOURCE: PARKING_SOURCE
  };
})(typeof window !== "undefined" ? window : globalThis);
