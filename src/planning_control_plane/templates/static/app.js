/* Planning Control Plane — generated site behaviour (UI V0.1.1 / V0.1.2).
 *
 * Progressive enhancement only: every page is complete and usable without
 * JavaScript (the tree renders fully expanded, decision groups are native
 * <details>, and all links are plain anchors). This script adds, in DOM
 * order:
 *
 *   1. Runtime language switching (V0.1.2). The page embeds the complete
 *      translation payload from the Python i18n dictionaries as
 *      <script type="application/json" id="pcp-i18n"> — there is no second
 *      translation table in this file. Elements marked `data-i18n` (text)
 *      and `data-i18n-attr` (attributes) are re-labelled from that payload;
 *      `<html lang>` follows the active locale. The choice persists in
 *      localStorage under `pcp.locale:<site>` — a browser-side preference
 *      that never reaches the generated files and never affects
 *      `pcp build --check`.
 *   2. Planning tree expand/collapse through a real toggle button per
 *      branch, with the open/closed set remembered in localStorage. The
 *      stored value is a pure UI preference: it never reaches the
 *      generated output and never affects `pcp build --check`.
 *   3. Expand all / collapse all, and auto-scrolling the sidebar to the
 *      node whose page is open.
 *   4. Copy buttons — context capsule and node id — using the async
 *      Clipboard API, announcing the result through an aria-live region
 *      and falling back to a selectable read-only textarea.
 *   5. Off-canvas sidebar on narrow screens, marked `inert` while hidden
 *      so keyboard focus cannot enter it.
 *
 * Vanilla JavaScript, no dependencies, no network requests.
 */
(function () {
  "use strict";

  var sidebar = document.getElementById("sidebar");
  var liveRegion = document.querySelector(".copy-status");

  /* ------------------------------------------------- runtime language (V0.1.2) --- */

  /* The payload is generated from planning_control_plane.i18n — the same
   * dictionaries that rendered the page — so Python stays the single
   * translation source (spec §5). A missing or corrupt payload simply
   * disables switching: the page keeps its build locale. */
  var i18n = loadI18n();
  var activeLocale = null;

  function loadI18n() {
    var node = document.getElementById("pcp-i18n");
    if (!node) {
      return null;
    }
    try {
      var data = JSON.parse(node.textContent);
      if (data && data.messages && data.messages.en) {
        return data;
      }
    } catch (err) {
      /* corrupt payload: fall through to "no switching" */
    }
    return null;
  }

  /* One key per generated site, so two projects opened from the same
   * origin (file:// included) do not share preferences. Node pages live
   * one directory down, so that level is stripped to keep the key stable —
   * the same computation as the inline boot script in <head>. */
  function siteKey() {
    return String(location.pathname).replace(/[^/]*$/, "").replace(/nodes\/$/, "");
  }

  var LOCALE_KEY = "pcp.locale:" + siteKey();

  function supportedLocales() {
    if (!i18n) {
      return [];
    }
    return i18n.locales || Object.keys(i18n.messages);
  }

  function readStoredLocale() {
    var locales = supportedLocales();
    try {
      var stored = window.localStorage.getItem(LOCALE_KEY);
      if (stored && locales.indexOf(stored) !== -1) {
        return stored;
      }
    } catch (err) {
      /* storage unavailable (private mode, file:// policy): use default */
    }
    return null;
  }

  function lookup(key, locale) {
    var table = i18n && i18n.messages ? i18n.messages[locale] : null;
    if (table && Object.prototype.hasOwnProperty.call(table, key)) {
      return table[key];
    }
    return null;
  }

  /* Mirrors the Python translator: current locale, then English, then the
   * key itself. `{name}` placeholders interpolate from parsed args. */
  function translate(key, args) {
    var text = lookup(key, activeLocale);
    if (text === null) {
      text = lookup(key, "en");
    }
    if (text === null) {
      return key;
    }
    if (!args) {
      return text;
    }
    return String(text).replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, function (whole, name) {
      return Object.prototype.hasOwnProperty.call(args, name) ? String(args[name]) : whole;
    });
  }

  function parseArgs(element) {
    var raw = element.getAttribute("data-i18n-args");
    if (!raw) {
      return null;
    }
    try {
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch (err) {
      return null; // a broken args blob must not blank the label
    }
  }

  /* `data-i18n-attr` is a ';'-separated list of attribute=key pairs, e.g.
   * "aria-label=action.copy_context.aria; data-copied-label=action.copied". */
  function applyAttrs(element) {
    var spec = element.getAttribute("data-i18n-attr") || "";
    spec.split(";").forEach(function (pair) {
      var parts = pair.split("=");
      if (parts.length !== 2) {
        return;
      }
      var name = parts[0].replace(/^\s+|\s+$/g, "");
      var key = parts[1].replace(/^\s+|\s+$/g, "");
      if (name && key) {
        element.setAttribute(name, translate(key));
      }
    });
  }

  function applyLocale(locale) {
    activeLocale = locale;
    var root = document.documentElement;
    root.lang = locale;
    root.setAttribute("data-locale", locale); // stylesheet reacts (raw-enum chips)

    Array.prototype.forEach.call(document.querySelectorAll("[data-i18n]"), function (element) {
      element.textContent = translate(element.getAttribute("data-i18n"), parseArgs(element));
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-i18n-attr]"), applyAttrs);

    var group = document.getElementById("lang-switch");
    if (group) {
      group.hidden = false; // without JavaScript the control would do nothing
    }
    Array.prototype.forEach.call(document.querySelectorAll("[data-set-locale]"), function (button) {
      var active = button.getAttribute("data-set-locale") === locale;
      button.setAttribute("aria-pressed", active ? "true" : "false");
      if (active) {
        button.classList.add("is-active");
      } else {
        button.classList.remove("is-active");
      }
    });
  }

  if (i18n) {
    applyLocale(readStoredLocale() || i18n.default || "en");

    Array.prototype.forEach.call(document.querySelectorAll("[data-set-locale]"), function (button) {
      button.addEventListener("click", function () {
        var locale = button.getAttribute("data-set-locale");
        if (supportedLocales().indexOf(locale) === -1) {
          return;
        }
        try {
          window.localStorage.setItem(LOCALE_KEY, locale);
        } catch (err) {
          /* preference-only: losing it must never break the switch itself */
        }
        applyLocale(locale);
      });
    });
  }

  /* ------------------------------------------------ stored preferences --- */

  function readCollapsed() {
    try {
      var raw = window.localStorage.getItem("pcp.tree:" + siteKey());
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return []; // storage unavailable (private mode, file:// policy): ignore
    }
  }

  function writeCollapsed(ids) {
    try {
      window.localStorage.setItem("pcp.tree:" + siteKey(), JSON.stringify(ids));
    } catch (err) {
      /* preference-only: losing it must never break the page */
    }
  }

  /* ------------------------------------------------------ planning tree --- */

  var branches = Array.prototype.slice.call(
    document.querySelectorAll('.treeitem[aria-expanded]')
  );

  function setExpanded(item, expanded) {
    item.setAttribute("aria-expanded", expanded ? "true" : "false");
    var toggle = item.querySelector(":scope > .treeitem-row > .tree-toggle");
    if (toggle && toggle.tagName === "BUTTON") {
      toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    }
  }

  function persist() {
    var collapsed = [];
    branches.forEach(function (item) {
      if (item.getAttribute("aria-expanded") === "false") {
        collapsed.push(item.getAttribute("data-node-id"));
      }
    });
    writeCollapsed(collapsed);
  }

  if (branches.length) {
    var collapsedIds = readCollapsed();
    branches.forEach(function (item) {
      if (collapsedIds.indexOf(item.getAttribute("data-node-id")) !== -1) {
        setExpanded(item, false);
      }
    });

    // Whatever the stored state says, the branch leading to the page you
    // are on is always visible.
    var currentItem = document.querySelector('.treeitem[data-current-page="true"]');
    if (currentItem) {
      var ancestor = currentItem.parentElement;
      while (ancestor && ancestor !== document.body) {
        if (ancestor.classList && ancestor.classList.contains("treeitem")) {
          setExpanded(ancestor, true);
        }
        ancestor = ancestor.parentElement;
      }
    }

    branches.forEach(function (item) {
      var toggle = item.querySelector(":scope > .treeitem-row > .tree-toggle");
      if (!toggle || toggle.tagName !== "BUTTON") {
        return;
      }
      toggle.addEventListener("click", function (event) {
        event.preventDefault();
        setExpanded(item, item.getAttribute("aria-expanded") !== "true");
        persist();
      });
    });

    Array.prototype.forEach.call(
      document.querySelectorAll("[data-tree-action]"),
      function (button) {
        button.addEventListener("click", function () {
          var expand = button.getAttribute("data-tree-action") === "expand";
          branches.forEach(function (item) {
            setExpanded(item, expand);
          });
          persist();
        });
      }
    );
  }

  /* Bring the open node into view inside the sidebar only — the main
   * document scroll position is left alone. */
  (function scrollCurrentIntoView() {
    if (!sidebar) {
      return;
    }
    var current = sidebar.querySelector('.treeitem[data-current-page="true"] > .treeitem-row');
    if (!current || sidebar.scrollHeight <= sidebar.clientHeight) {
      return;
    }
    var target = current.offsetTop - sidebar.clientHeight / 2 + current.offsetHeight / 2;
    sidebar.scrollTop = Math.max(0, target);
  }());

  /* ------------------------------------------------------------- copying --- */

  function announce(message) {
    if (liveRegion) {
      liveRegion.textContent = message;
    }
  }

  function fallbackFor(button) {
    var scope = button.closest("section") || document;
    return scope.querySelector(".copy-fallback") || document.querySelector(".copy-fallback");
  }

  function showFallback(button) {
    var fallback = fallbackFor(button);
    if (!fallback) {
      return;
    }
    fallback.hidden = false;
    var area = fallback.querySelector("textarea");
    if (area) {
      area.focus();
      area.select();
    }
  }

  Array.prototype.forEach.call(
    document.querySelectorAll("[data-copy-from], [data-copy-value]"),
    function (button) {
      // Build-locale label, kept as the last-resort revert text if the
      // translation payload is unavailable.
      var originalLabel = button.textContent;
      var revertTimer = null;

      // Read labels at click time, not setup time, so they follow the
      // currently active locale (the switch rewrites data-i18n text and
      // the data-copied-label attribute).
      function idleLabel() {
        var key = button.getAttribute("data-i18n");
        var text = key ? translate(key) : null;
        return text && text !== key ? text : originalLabel;
      }

      function resolveText() {
        var literal = button.getAttribute("data-copy-value");
        if (literal !== null) {
          return literal;
        }
        var source = document.getElementById(button.getAttribute("data-copy-from"));
        return source ? source.textContent : "";
      }

      function markCopied() {
        var idle = idleLabel();
        var copied = button.getAttribute("data-copied-label") || idle;
        button.textContent = copied;
        announce(copied);
        if (revertTimer !== null) {
          window.clearTimeout(revertTimer);
        }
        revertTimer = window.setTimeout(function () {
          button.textContent = idleLabel();
          revertTimer = null;
        }, 2000);
      }

      button.addEventListener("click", function () {
        var text = resolveText();
        if (!text) {
          showFallback(button);
          return;
        }
        if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
          showFallback(button);
          return;
        }
        navigator.clipboard.writeText(text).then(markCopied, function () {
          showFallback(button);
        });
      });
    }
  );

  /* -------------------------------------------- sidebar (narrow screens) - */

  var sidebarToggle = document.getElementById("sidebar-toggle");
  if (sidebarToggle && sidebar) {
    var narrow = window.matchMedia("(max-width: 960px)");

    function sidebarOpen() {
      return document.body.classList.contains("sidebar-open");
    }

    /* An off-canvas sidebar must not hold keyboard focus. CSS already
     * takes it out of the tab order; `inert` also hides it from assistive
     * technology in browsers that support it. */
    function syncInert() {
      if (narrow.matches && !sidebarOpen()) {
        sidebar.setAttribute("inert", "");
      } else {
        sidebar.removeAttribute("inert");
      }
    }

    function closeSidebar() {
      document.body.classList.remove("sidebar-open");
      sidebarToggle.setAttribute("aria-expanded", "false");
      syncInert();
    }

    sidebarToggle.addEventListener("click", function () {
      var open = document.body.classList.toggle("sidebar-open");
      sidebarToggle.setAttribute("aria-expanded", open ? "true" : "false");
      syncInert();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && sidebarOpen()) {
        closeSidebar();
        sidebarToggle.focus();
      }
    });

    document.addEventListener("click", function (event) {
      if (!sidebarOpen()) {
        return;
      }
      if (sidebar.contains(event.target) || sidebarToggle.contains(event.target)) {
        return;
      }
      closeSidebar();
    });

    if (typeof narrow.addEventListener === "function") {
      narrow.addEventListener("change", syncInert);
    } else if (typeof narrow.addListener === "function") {
      narrow.addListener(syncInert); // older Safari
    }
    syncInert();
  }
}());
