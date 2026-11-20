// Small interface helpers shared by every page: toasts, dialogs and the
// collapsible navigation. No dependencies.
(function () {
  "use strict";

  // Shows a short message in the corner of the screen.
  function toast(message, type) {
    var host = document.getElementById("toasts");
    if (!host) {
      return;
    }
    var el = document.createElement("div");
    el.className = "toast" + (type === "error" ? " error" : "");
    el.textContent = message;
    host.appendChild(el);
    setTimeout(function () {
      el.remove();
    }, type === "error" ? 6000 : 3500);
  }

  // Opens a <dialog class="modal">. `onClose` runs once when it closes,
  // whatever closed it (button, Escape or a click outside).
  function openModal(dialog, onClose) {
    if (!dialog || dialog.open) {
      return;
    }
    if (onClose) {
      dialog.addEventListener("close", onClose, { once: true });
    }
    dialog.showModal();
  }

  function closeModal(dialog) {
    if (dialog && dialog.open) {
      dialog.close();
    }
  }

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-modal-open]");
    if (opener) {
      event.preventDefault();
      openModal(document.getElementById(opener.getAttribute("data-modal-open")));
      return;
    }
    var closer = event.target.closest("[data-modal-close]");
    if (closer) {
      event.preventDefault();
      closeModal(closer.closest("dialog"));
      return;
    }
    // A click on the backdrop lands on the <dialog> element itself.
    if (event.target.matches && event.target.matches("dialog.modal")) {
      closeModal(event.target);
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.querySelector("[data-nav-toggle]");
    var panel = document.getElementById("nav-panel");
    if (toggle && panel) {
      toggle.addEventListener("click", function () {
        var open = panel.classList.toggle("open");
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }
  });

  window.UI = { toast: toast, openModal: openModal, closeModal: closeModal };
})();
