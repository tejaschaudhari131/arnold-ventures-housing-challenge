/* Shared number formatters and focusable tooltips. No model results live here. */
(function (root) {
  "use strict";

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function finite(value) {
    var n = Number(value);
    return isFinite(n) ? n : null;
  }

  function grouped(value) {
    var n = Math.round(Math.abs(Number(value)));
    return n.toLocaleString("en-US");
  }

  function homes(value) {
    var n = finite(value);
    if (n === null) return "No data";
    return (n < 0 ? "−" : "") + grouped(n);
  }

  function signedHomes(value) {
    var n = finite(value);
    if (n === null) return "No data";
    if (n > 0) return "+" + grouped(n);
    if (n < 0) return "−" + grouped(n);
    return "0";
  }

  function rangeText(low, high) {
    var a = finite(low);
    var b = finite(high);
    if (a === null || b === null) return "Likely range unavailable";
    if (a <= 0 || b <= 0) return homes(a) + " to " + homes(b);
    return homes(a) + "–" + homes(b);
  }

  function percent(share, digits) {
    var n = finite(share);
    if (n === null) return "No data";
    var pct = n * 100;
    var places = digits;
    if (places == null) places = Math.abs(pct) > 0 && Math.abs(pct) < 10 ? 1 : 0;
    return pct.toFixed(places) + "%";
  }

  function money(value, per) {
    var n = finite(value);
    if (n === null) return "No data";
    var text = (n < 0 ? "−" : "") + "$" + grouped(n);
    return per ? text + " " + per : text;
  }

  function bind(path, text) {
    return '<span data-bind="' + esc(path) + '">' + text + "</span>";
  }

  var tipSerial = 0;

  function tipButton(label, tip, className) {
    if (!tip) return esc(label);
    var id = "tip-" + (++tipSerial);
    return '<button type="button" class="tip' + (className ? " " + className : "") +
      '" aria-describedby="' + id + '" aria-expanded="false">' + esc(label) +
      '</button><span class="tip-pop" id="' + id + '" role="tooltip" hidden>' + esc(tip) + "</span>";
  }

  function closeTips(doc) {
    (doc || document).querySelectorAll("button.tip[aria-expanded='true']").forEach(function (btn) {
      btn.setAttribute("aria-expanded", "false");
      var pop = (doc || document).getElementById(btn.getAttribute("aria-describedby"));
      if (pop) pop.hidden = true;
    });
  }

  function openTip(btn) {
    if (!btn) return;
    var doc = btn.ownerDocument || document;
    closeTips(doc);
    btn.setAttribute("aria-expanded", "true");
    var pop = doc.getElementById(btn.getAttribute("aria-describedby"));
    if (pop) pop.hidden = false;
  }

  function upgradeTitles(root) {
    if (!root || !root.querySelectorAll) return;
    var nodes = root.querySelectorAll("[title]");
    Array.prototype.forEach.call(nodes, function (node) {
      if (!node.getAttribute) return;
      if (node.namespaceURI && String(node.namespaceURI).indexOf("svg") >= 0) return;
      if (node.closest && node.closest("svg")) return;
      var tip = node.getAttribute("title");
      if (!tip) return;
      node.removeAttribute("title");
      var id = "tip-" + (++tipSerial);
      var btn = root.ownerDocument ? root.ownerDocument.createElement("button") : document.createElement("button");
      var pop = root.ownerDocument ? root.ownerDocument.createElement("span") : document.createElement("span");
      var doc = node.ownerDocument || document;
      btn = doc.createElement("button");
      pop = doc.createElement("span");
      btn.type = "button";
      btn.className = "tip";
      btn.setAttribute("aria-describedby", id);
      btn.setAttribute("aria-expanded", "false");
      btn.textContent = (node.textContent || "Note").trim() || "Note";
      pop.className = "tip-pop";
      pop.id = id;
      pop.setAttribute("role", "tooltip");
      pop.hidden = true;
      pop.textContent = tip;
      if (!node.querySelector || !node.querySelector("*")) node.textContent = "";
      node.appendChild(btn);
      node.appendChild(pop);
    });
  }

  function bindTips(doc) {
    doc = doc || document;
    if (!doc || doc.__sfTips) return;
    doc.__sfTips = true;
    upgradeTitles(doc);
    doc.addEventListener("focusin", function (event) {
      var btn = event.target.closest ? event.target.closest("button.tip") : null;
      if (!btn) {
        closeTips(doc);
        return;
      }
      openTip(btn);
    });
    doc.addEventListener("click", function (event) {
      var btn = event.target.closest ? event.target.closest("button.tip") : null;
      if (!btn) {
        closeTips(doc);
        return;
      }
      event.preventDefault();
      var open = btn.getAttribute("aria-expanded") === "true";
      closeTips(doc);
      if (!open) openTip(btn);
    });
    doc.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      if (!doc.querySelector("button.tip[aria-expanded='true']")) return;
      event.preventDefault();
      closeTips(doc);
    });
    if (typeof MutationObserver === "function" && doc.body) {
      var pending = false;
      var observer = new MutationObserver(function () {
        if (pending) return;
        pending = true;
        setTimeout(function () {
          pending = false;
          upgradeTitles(doc);
        }, 0);
      });
      observer.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["title"] });
    }
  }

  root.StateframeFmt = {
    esc: esc,
    homes: homes,
    signedHomes: signedHomes,
    rangeText: rangeText,
    percent: percent,
    money: money,
    bind: bind,
    tipButton: tipButton,
    upgradeTitles: upgradeTitles,
    bindTips: bindTips,
    closeTips: closeTips
  };
})(typeof window !== "undefined" ? window : globalThis);
