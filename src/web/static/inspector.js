/* Live click-any-number provenance and equation lineage inspector.
   Reads existing data-bind, data-derived, and .num provenance badges. */
(function (root) {
  "use strict";

  var active = false;
  var popover = null;
  var lastTrigger = null;

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function classifyPath(path, derivedFrom, nearTag) {
    if (nearTag === "observed" || nearTag === "assumed" || nearTag === "calculated") {
      return nearTag;
    }
    var p = String(path || derivedFrom || "");
    if (!p) return "calculated";
    if (
      p.indexOf("by_name.") === 0 ||
      p.indexOf("anchors.") === 0 ||
      /\.p10$|\.p90$|_fee$|cap_rate|rent_ratio/.test(p)
    ) {
      return "assumed";
    }
    if (/acs_moe|coverage\.|housing_units|permit_vintage/.test(p)) {
      return "observed";
    }
    return "calculated";
  }

  function describeOrigin(path, derived, isLab) {
    var p = String(path || "");
    if (derived) {
      return {
        code: isLab ? "src/lab/explain.py · src/web/static/frame.js" : "src/model/equations.py",
        data: "Derived directly on-screen from bound model outputs (" + derived + ")."
      };
    }
    if (p.indexOf("mix.") === 0) {
      return {
        code: "src/lab/explain.py (evaluate_mix) → src/lab/engine.py",
        data: "Live joint lot-by-lot county evaluation via POST /api/lab/mix."
      };
    }
    if (p.indexOf("by_name.") === 0 || p.indexOf("anchors.") === 0) {
      return {
        code: "config/lab/assumptions.yaml",
        data: "Published assumption band with documented literature & statutory rationale."
      };
    }
    if (p.indexOf("completion_ratios.") === 0) {
      return {
        code: "config/assumptions.yaml",
        data: "Published permit-to-completion ratio shared across models."
      };
    }
    if (p.indexOf("display_numbers.") === 0) {
      return {
        code: "src/adu_fee_note.py (comparison)",
        data: "Step-by-step model reconciliation between County Lab and 11-State Screening."
      };
    }
    if (p.indexOf("crossval_tier1.") === 0) {
      return {
        code: "src/model/crossval.py",
        data: "Tier-1 parcel extract vs. Tier-2 Census-imputed cross-check (CT, WI, UT, HI)."
      };
    }
    if (p.indexOf("statewide.") === 0 || p.indexOf("counties.") === 0) {
      return {
        code: "src/lab/engine.py · src/lab/uncertainty.py",
        data: "Locked 2,000-draw & county lot simulation (data/sample/lab/results_*.json, SHA-256 verified)."
      };
    }
    if (p.indexOf("scenarios.") === 0 || p === "baseline_completions_5yr") {
      return {
        code: "src/model/equations.py · src/model/engine.py",
        data: "11-state structural county pro forma summed to state total (ACS + Census BPS)."
      };
    }
    return {
      code: isLab ? "src/lab/engine.py" : "src/model/equations.py",
      data: "Public Census ACS, Building Permits Survey, and published config/assumptions.yaml."
    };
  }

  function ensurePopover() {
    if (popover) return popover;
    popover = document.createElement("aside");
    popover.id = "lineage-popover";
    popover.className = "lineage-popover no-print";
    popover.setAttribute("role", "dialog");
    popover.setAttribute("aria-modal", "false");
    popover.setAttribute("aria-label", "Number provenance and equation lineage");
    popover.hidden = true;
    document.body.appendChild(popover);
    return popover;
  }

  function closePopover() {
    if (!popover || popover.hidden) return;
    popover.hidden = true;
    if (lastTrigger && typeof lastTrigger.focus === "function") {
      try {
        lastTrigger.focus({ preventScroll: true });
      } catch (_err) {
        lastTrigger.focus();
      }
    }
    lastTrigger = null;
  }

  function findBoundTarget(node) {
    if (!node || !node.closest) return null;
    return node.closest("[data-bind], [data-derived], .num");
  }

  function extractNearTag(target) {
    var abbr = target.querySelector && target.querySelector(".tag");
    if (!abbr && target.nextElementSibling && target.nextElementSibling.classList && target.nextElementSibling.classList.contains("tag")) {
      abbr = target.nextElementSibling;
    }
    if (!abbr && target.parentElement) {
      abbr = target.parentElement.querySelector(".tag");
    }
    if (!abbr) return "";
    var txt = String(abbr.textContent || "").trim().toLowerCase();
    return (txt === "observed" || txt === "assumed" || txt === "calculated") ? txt : "";
  }

  function cleanDisplayValue(target) {
    var clone = target.cloneNode(true);
    var tags = clone.querySelectorAll ? clone.querySelectorAll(".tag") : [];
    Array.prototype.forEach.call(tags, function (t) {
      if (t.parentNode) t.parentNode.removeChild(t);
    });
    return String(clone.textContent || "").replace(/\s+/g, " ").trim();
  }

  function showLineage(target, event) {
    var box = ensurePopover();
    var isLab = !!document.getElementById("why-toggle");
    var path = target.getAttribute("data-bind") || "";
    var derived = target.getAttribute("data-derived") || "";
    var derivedFrom = target.getAttribute("data-from") || "";
    var nearTag = extractNearTag(target);
    var tag = classifyPath(path, derivedFrom, nearTag);
    var valueText = cleanDisplayValue(target) || "—";
    var origin = describeOrigin(path, derived ? (derived + (derivedFrom ? " ← " + derivedFrom : "")) : "", isLab);
    var jumpLabel = isLab ? "Open county Why drawer" : "Open Show the math";

    box.innerHTML =
      '<div class="lineage-head">' +
        '<strong>Number lineage</strong> ' +
        '<abbr class="tag ' + esc(tag) + '">' + esc(tag) + "</abbr>" +
      "</div>" +
      '<p class="lineage-val">' + esc(valueText) + "</p>" +
      (path ? '<p class="lineage-meta"><span>Binding path:</span> <code>' + esc(path) + "</code></p>" : "") +
      (derived ? '<p class="lineage-meta"><span>Derived rule:</span> <code>' + esc(derived + (derivedFrom ? " (" + derivedFrom + ")" : "")) + "</code></p>" : "") +
      '<p class="lineage-meta"><span>Engine module:</span> <code>' + esc(origin.code) + "</code></p>" +
      '<p class="lineage-meta"><span>Data &amp; method:</span> ' + esc(origin.data) + "</p>" +
      '<div class="lineage-actions">' +
        '<button type="button" class="btn pri lineage-jump">' + esc(jumpLabel) + "</button>" +
        '<button type="button" class="lineage-close">Close (Esc)</button>' +
      "</div>";

    box.hidden = false;
    lastTrigger = target;

    var minTop = 16;
    var suiteBar = document.querySelector(".suite-bar");
    if (suiteBar && typeof suiteBar.getBoundingClientRect === "function") {
      var sbRect = suiteBar.getBoundingClientRect();
      if (sbRect.height > 4 && sbRect.bottom > 0) minTop = Math.max(minTop, Math.ceil(sbRect.bottom) + 10);
    }
    var miniBar = document.getElementById("mini-total");
    if (miniBar && !miniBar.hidden && typeof miniBar.getBoundingClientRect === "function") {
      var barRect = miniBar.getBoundingClientRect();
      if (barRect.height > 4) minTop = Math.max(minTop, Math.ceil(barRect.bottom) + 12);
    }
    var rect = target.getBoundingClientRect ? target.getBoundingClientRect() : { left: 24, bottom: 80 };
    var top = Math.min(Math.max(minTop, window.innerHeight - 250), Math.max(minTop, rect.bottom + 8));
    var left = Math.min(window.innerWidth - 360, Math.max(16, rect.left));
    box.style.top = top + "px";
    box.style.left = left + "px";

    var jumpBtn = box.querySelector(".lineage-jump");
    if (jumpBtn) {
      jumpBtn.addEventListener("click", function () {
        closePopover();
        if (isLab) {
          var whyToggle = document.getElementById("why-toggle");
          var whyDrawer = document.getElementById("why");
          if (whyToggle && whyDrawer && whyDrawer.hidden) whyToggle.click();
          if (whyDrawer && whyDrawer.scrollIntoView) whyDrawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
        } else {
          var mathTab = document.getElementById("tab-math");
          var mathPanel = document.getElementById("panel-math");
          if (mathTab) mathTab.click();
          if (mathPanel && mathPanel.scrollIntoView) mathPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }
    var closeBtn = box.querySelector(".lineage-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", closePopover);
      try {
        closeBtn.focus({ preventScroll: true });
      } catch (_err) {
        closeBtn.focus();
      }
    }
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
  }

  function setInspectMode(next) {
    active = !!next;
    if (document.body && document.body.classList) {
      document.body.classList.toggle("inspect-on", active);
    }
    var btn = document.getElementById("inspect-toggle");
    if (btn) {
      btn.setAttribute("aria-pressed", active ? "true" : "false");
      btn.textContent = active ? "Inspect numbers: On (click any figure)" : "Inspect numbers: Off";
    }
    if (!active) closePopover();
  }

  function mountToggle() {
    if (!document || !document.querySelector) return;
    var bar = document.querySelector(".legend-bar");
    if (!bar || document.getElementById("inspect-toggle")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.id = "inspect-toggle";
    btn.className = "inspect-toggle";
    btn.setAttribute("aria-pressed", "false");
    btn.textContent = "Inspect numbers: Off";
    btn.addEventListener("click", function () {
      setInspectMode(!active);
    });
    bar.appendChild(document.createTextNode(" · "));
    bar.appendChild(btn);
  }

  if (typeof document !== "undefined" && document.addEventListener) {
    mountToggle();
    document.addEventListener("click", function (event) {
      if (popover && !popover.hidden && popover.contains && popover.contains(event.target)) {
        return;
      }
      var target = findBoundTarget(event.target);
      if (target && (active || event.altKey)) {
        showLineage(target, event);
        return;
      }
      if (popover && !popover.hidden) {
        closePopover();
      }
    }, true);

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && popover && !popover.hidden) {
        event.preventDefault();
        closePopover();
      }
    });
  }

  root.StateframeInspector = {
    classifyPath: classifyPath,
    describeOrigin: describeOrigin,
    setInspectMode: setInspectMode,
    isActive: function () { return active; }
  };
})(typeof window !== "undefined" ? window : globalThis);
