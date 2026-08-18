/* Planning Control Plane — generated site behaviour.
 *
 * Progressive enhancement only: every page is complete and usable without
 * JavaScript (the tree renders fully expanded and all links are plain
 * anchors). This script adds three behaviours, in DOM order:
 *
 *   1. Planning tree expand/collapse — click on a branch row, or focus the
 *      row and press Enter/Space. State lives in aria-expanded, so CSS and
 *      assistive technology stay in sync for free.
 *   2. "Copy Context" button on node pages — uses the async Clipboard API
 *      when available; on failure or absence it reveals a read-only
 *      textarea with the same content, focused and selected for a manual
 *      copy.
 *   3. Off-canvas sidebar toggle on narrow screens.
 *
 * Vanilla JavaScript, no dependencies, no network requests.
 */
(function () {
  "use strict";

  /* ------------------------------------------------ planning tree --------- */

  function toggleTreeItem(item) {
    var expanded = item.getAttribute("aria-expanded") === "true";
    item.setAttribute("aria-expanded", expanded ? "false" : "true");
  }

  var treeItems = document.querySelectorAll('[role="treeitem"]');
  Array.prototype.forEach.call(treeItems, function (item) {
    if (!item.hasAttribute("aria-expanded")) {
      return; // leaf: nothing to toggle
    }
    item.addEventListener("click", function (event) {
      if (event.defaultPrevented) {
        return;
      }
      // Clicks on links (and other controls) keep their native behaviour.
      if (event.target.closest("a, button, input, textarea, select")) {
        return;
      }
      toggleTreeItem(item);
    });
    item.addEventListener("keydown", function (event) {
      // Only when the treeitem itself is focused; a focused inner link
      // keeps native Enter-to-navigate.
      if (event.target !== item) {
        return;
      }
      if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
        event.preventDefault();
        toggleTreeItem(item);
      }
    });
  });

  /* ------------------------------------------------- copy context -------- */

  var copyButton = document.querySelector(".copy-context");
  if (copyButton) {
    var panel = copyButton.closest(".resume");
    var capsule = panel ? panel.querySelector("pre.capsule-text") : null;
    var fallback = panel ? panel.querySelector(".copy-fallback") : null;
    var text = capsule ? capsule.textContent : "";

    var originalLabel = copyButton.textContent;
    var revertTimer = null;

    function showFallback() {
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

    function markCopied() {
      copyButton.textContent = "Copied";
      if (revertTimer !== null) {
        window.clearTimeout(revertTimer);
      }
      revertTimer = window.setTimeout(function () {
        copyButton.textContent = originalLabel;
        revertTimer = null;
      }, 2000);
    }

    copyButton.addEventListener("click", function () {
      if (!text) {
        showFallback();
        return;
      }
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
        showFallback();
        return;
      }
      navigator.clipboard.writeText(text).then(markCopied, showFallback);
    });
  }

  /* -------------------------------------------- sidebar (narrow screens) - */

  var sidebarToggle = document.getElementById("sidebar-toggle");
  var sidebar = document.getElementById("sidebar");
  if (sidebarToggle && sidebar) {
    function sidebarOpen() {
      return document.body.classList.contains("sidebar-open");
    }

    function closeSidebar() {
      document.body.classList.remove("sidebar-open");
      sidebarToggle.setAttribute("aria-expanded", "false");
    }

    sidebarToggle.addEventListener("click", function () {
      var open = document.body.classList.toggle("sidebar-open");
      sidebarToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && sidebarOpen()) {
        closeSidebar();
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
  }
}());
