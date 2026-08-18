/* Planning Control Plane — generated site behaviour (UI V0.1.1).
 *
 * Progressive enhancement only: every page is complete and usable without
 * JavaScript (the tree renders fully expanded, decision groups are native
 * <details>, and all links are plain anchors). This script adds, in DOM
 * order:
 *
 *   1. Planning tree expand/collapse through a real toggle button per
 *      branch, with the open/closed set remembered in localStorage. The
 *      stored value is a pure UI preference: it never reaches the
 *      generated output and never affects `pcp build --check`.
 *   2. Expand all / collapse all, and auto-scrolling the sidebar to the
 *      node whose page is open.
 *   3. Copy buttons — context capsule and node id — using the async
 *      Clipboard API, announcing the result through an aria-live region
 *      and falling back to a selectable read-only textarea.
 *   4. Off-canvas sidebar on narrow screens, marked `inert` while hidden
 *      so keyboard focus cannot enter it.
 *
 * Vanilla JavaScript, no dependencies, no network requests.
 */
(function () {
  "use strict";

  var sidebar = document.getElementById("sidebar");
  var liveRegion = document.querySelector(".copy-status");

  /* ------------------------------------------------ stored preferences --- */

  /* One key per generated site, so two projects opened from the same
   * origin (file:// included) do not share tree state. Node pages live one
   * directory down, so that level is stripped to keep the key stable. */
  function storageKey() {
    var dir = String(location.pathname).replace(/[^/]*$/, "");
    return "pcp.tree:" + dir.replace(/nodes\/$/, "");
  }

  function readCollapsed() {
    try {
      var raw = window.localStorage.getItem(storageKey());
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return []; // storage unavailable (private mode, file:// policy): ignore
    }
  }

  function writeCollapsed(ids) {
    try {
      window.localStorage.setItem(storageKey(), JSON.stringify(ids));
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
      var originalLabel = button.textContent;
      var copiedLabel = button.getAttribute("data-copied-label") || originalLabel;
      var revertTimer = null;

      function resolveText() {
        var literal = button.getAttribute("data-copy-value");
        if (literal !== null) {
          return literal;
        }
        var source = document.getElementById(button.getAttribute("data-copy-from"));
        return source ? source.textContent : "";
      }

      function markCopied() {
        button.textContent = copiedLabel;
        announce(copiedLabel);
        if (revertTimer !== null) {
          window.clearTimeout(revertTimer);
        }
        revertTimer = window.setTimeout(function () {
          button.textContent = originalLabel;
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
