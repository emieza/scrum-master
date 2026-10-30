(function () {
  "use strict";

  function init() {
    var group = document.getElementById("specs-group");
    var toggleAll = document.getElementById("toggle-all-specs");
    if (!group || !toggleAll) {
      return;
    }

    var collapsedRowClass = "spec-collapsed";

    function rows() {
      return Array.from(
        group.querySelectorAll(".inline-related:not(.empty-form)")
      );
    }

    function isCollapsed(row) {
      return row.classList.contains(collapsedRowClass);
    }

    function setRowCollapsed(row, collapsed) {
      row.classList.toggle(collapsedRowClass, collapsed);
      var link = row.querySelector("h3 > .spec-collapse-toggle");
      if (link) {
        link.textContent = collapsed ? "Desplega" : "Col·lapsa";
        link.setAttribute("aria-expanded", collapsed ? "false" : "true");
      }
    }

    function allCollapsed() {
      var list = rows();
      return list.length > 0 && list.every(isCollapsed);
    }

    function syncToggleAll() {
      var collapsed = allCollapsed();
      toggleAll.textContent = collapsed
        ? "Desplega totes les specs"
        : "Col·lapsa totes les specs";
      toggleAll.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }

    function addRowToggle(row) {
      var heading = row.querySelector(":scope > h3");
      if (!heading || heading.querySelector(".spec-collapse-toggle")) {
        return;
      }
      var link = document.createElement("a");
      link.href = "#";
      link.className = "spec-collapse-toggle";
      link.textContent = "Col·lapsa";
      link.setAttribute("aria-expanded", "true");
      link.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        setRowCollapsed(row, !isCollapsed(row));
        syncToggleAll();
      });
      link.addEventListener("mousedown", function (event) {
        event.stopPropagation();
      });
      heading.appendChild(link);
    }

    function addToggles() {
      rows().forEach(addRowToggle);
      syncToggleAll();
    }

    addToggles();

    var observer = new MutationObserver(addToggles);
    observer.observe(group, { childList: true, subtree: true });

    toggleAll.addEventListener("click", function (event) {
      event.preventDefault();
      var collapse = !allCollapsed();
      rows().forEach(function (row) {
        setRowCollapsed(row, collapse);
      });
      syncToggleAll();
      if (collapse) {
        group.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
