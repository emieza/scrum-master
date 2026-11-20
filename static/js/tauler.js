// Kanban board of a team: moving cards, the task dialog and the automatic
// refresh. The server decides what is allowed; this file only sends the
// action and repaints the columns it gets back.
(function () {
  "use strict";

  var tauler = document.getElementById("tauler");
  if (!tauler) {
    return;
  }

  var base = tauler.dataset.base; // …/equips/<id>/tauler
  var versio = Number(tauler.dataset.versio) || 0;
  var interval = Number(tauler.dataset.interval) || 0;
  var potEditar = tauler.dataset.potEditar === "1";
  var esProfe = tauler.dataset.esProfe === "1";
  var modalTasca = document.getElementById("modal-tasca");
  var contingut = document.getElementById("tasca-contingut");
  var modalMotiu = document.getElementById("modal-motiu");
  var formMotiu = document.getElementById("form-motiu");
  var motiuText = document.getElementById("motiu-text");
  var filtre = document.getElementById("filtre-sprint");
  var edicio = document.getElementById("permet-edicio");
  var specOberta = null;
  var pestanya = "descripcio";
  var drag = null; // The card being carried, if any (see aixeca).
  var pendent = null; // A press that may still become a drag.
  var provisional = false; // A card shown in "Bloquejat" while its reason is asked.
  var aterrat = null; // { spec, x, y }: where the last dropped card was left.
  var aterratge = Promise.resolve(); // Resolves when the last glide is over.

  // Nothing may redraw the board under the user's hands.
  function ocupat() {
    return Boolean(drag || pendent || provisional);
  }

  function cookie(nom) {
    var parts = ("; " + document.cookie).split("; " + nom + "=");
    return parts.length === 2 ? parts.pop().split(";").shift() : "";
  }

  // Teachers open boards read-only and must switch editing on.
  function edicioActiva() {
    return potEditar && (!esProfe || (edicio && edicio.checked));
  }

  function aplicaEdicio() {
    tauler.classList.toggle("nomes-lectura", !edicioActiva());
    if (modalTasca) {
      modalTasca.classList.toggle("nomes-lectura", !edicioActiva());
    }
    tauler.querySelectorAll(".task-card").forEach(function (targeta) {
      var mobil = edicioActiva() && targeta.querySelector("[data-mou]") !== null;
      targeta.classList.toggle("can-drag", mobil);
    });
  }

  function aplicaFiltre() {
    var valor = filtre ? filtre.value : "";
    // The dimmed copy of a carried card is not a task: it is left alone.
    tauler.querySelectorAll(".task-card:not(.drag-ghost)").forEach(function (targeta) {
      var sprints = targeta.dataset.sprints ? targeta.dataset.sprints.split(",") : [];
      var visible =
        !valor ||
        (valor === "backlog" ? sprints.length === 0 : sprints.indexOf(valor) !== -1);
      targeta.hidden = !visible;
    });
    tauler.querySelectorAll(".column").forEach(function (columna) {
      var visibles = columna.querySelectorAll(".task-card:not([hidden]):not(.drag-ghost)").length;
      columna.querySelector(".count").textContent = visibles;
    });
  }

  function pinta(dades) {
    tauler.innerHTML = dades.html;
    versio = dades.versio;
    aplicaEdicio();
    aplicaFiltre();
    if (aterrat) {
      var targeta = tauler.querySelector('.task-card[data-spec="' + aterrat.spec + '"]');
      if (targeta && !targeta.hidden) {
        aterra(targeta, aterrat);
      }
      aterrat = null;
    }
  }

  function envia(spec, accio, camps) {
    var cos = new URLSearchParams(camps || {});
    return fetch(base + "/tasques/" + spec + "/" + accio, {
      method: "POST",
      headers: {
        "X-CSRFToken": cookie("csrftoken"),
        "X-Requested-With": "XMLHttpRequest"
      },
      body: cos
    })
      .then(function (resposta) {
        return resposta.json().catch(function () {
          return { ok: false, error: "No s'ha pogut fer l'acció (" + resposta.status + ")." };
        });
      })
      .then(function (dades) {
        if (!dades.ok) {
          UI.toast(dades.error || "No s'ha pogut fer l'acció.", "error");
          return false;
        }
        pinta(dades);
        if (specOberta !== null) {
          carregaTasca(specOberta);
        }
        return true;
      })
      .catch(function () {
        UI.toast("No s'ha pogut connectar amb el servidor.", "error");
        return false;
      });
  }

  function refresca() {
    return fetch(base + "/columnes")
      .then(function (resposta) { return resposta.json(); })
      .then(function (dades) {
        if (dades.ok) {
          pinta(dades);
        }
      })
      .catch(function () {});
  }

  // ---- Moving a task -----------------------------------------------------

  // Asks why a task is blocked. Resolves with the reason, or with null when
  // the form is closed without giving one.
  function demanaMotiu() {
    return new Promise(function (resol) {
      var resolt = false;
      function acaba(valor) {
        if (resolt) {
          return;
        }
        resolt = true;
        formMotiu.removeEventListener("submit", enviat);
        resol(valor);
      }
      function enviat(event) {
        event.preventDefault();
        var motiu = motiuText.value.trim();
        if (!motiu) {
          return;
        }
        acaba(motiu);
        UI.closeModal(modalMotiu);
      }
      motiuText.value = "";
      formMotiu.addEventListener("submit", enviat);
      UI.openModal(modalMotiu, function () {
        acaba(null);
      });
      motiuText.focus();
    });
  }

  // Used by the "Mou a…" list of a card and by the buttons of the task dialog.
  function mou(spec, estat) {
    if (!estat) {
      return;
    }
    if (estat === "bloquejat") {
      // Blocking always asks why.
      demanaMotiu().then(function (motiu) {
        if (motiu) {
          envia(spec, "mou", { estat: estat, motiu: motiu });
        }
      });
      return;
    }
    envia(spec, "mou", { estat: estat });
  }

  tauler.addEventListener("change", function (event) {
    var select = event.target.closest("[data-mou]");
    if (!select) {
      return;
    }
    var estat = select.value;
    select.value = "";
    mou(select.dataset.mou, estat);
  });

  // ---- Dragging a card to another column -----------------------------------
  // Done with pointer events, so the same code serves a mouse, a pen and a
  // finger. With a mouse the card lifts as soon as it is pressed and moves
  // once it is pulled; on a touch screen it lifts after a long press, so a
  // plain swipe still scrolls the board. The carried card is a little bigger
  // with a deeper shadow, and a dimmed copy keeps the place it left.
  var LONG_PRESS_MS = 350;
  var PULL_PX = 5; // Mouse: how far the card is pulled before it moves.
  var SLOP_PX = 10; // Touch: moving this far before the long press is a scroll.

  function centre(el) {
    var caixa = el.getBoundingClientRect();
    return { x: caixa.left + caixa.width / 2, y: caixa.top + caixa.height / 2 };
  }

  // The states a card may be moved to: the options of its "Mou a…" list,
  // which the server wrote for the person looking at the board.
  function permesos(targeta) {
    var opcions = targeta.querySelectorAll("[data-mou] option");
    return Array.prototype.map
      .call(opcions, function (opcio) { return opcio.value; })
      .filter(Boolean);
  }

  function columnaA(x, y) {
    return Array.prototype.find.call(tauler.querySelectorAll(".column"), function (columna) {
      var caixa = columna.getBoundingClientRect();
      return x >= caixa.left && x <= caixa.right && y >= caixa.top && y <= caixa.bottom;
    });
  }

  function segueix() {
    drag.el.style.setProperty(
      "transform",
      "translate(" + (drag.x - drag.startX) + "px, " + (drag.y - drag.startY) + "px)"
    );
    var sobre = columnaA(drag.x, drag.y);
    var estat = sobre && drag.permesos.indexOf(sobre.dataset.estat) !== -1 ? sobre.dataset.estat : null;
    if (estat === drag.desti) {
      return;
    }
    drag.desti = estat;
    tauler.querySelectorAll(".drop-ok").forEach(function (columna) {
      columna.classList.remove("drop-ok");
    });
    if (estat) {
      sobre.classList.add("drop-ok");
    }
  }

  // Near an edge the board (sideways) and the page (up and down) scroll by themselves.
  function desplacaSol() {
    if (!drag) {
      return;
    }
    var vora = 60;
    var velocitat = function (distancia) { return Math.ceil(distancia / 5); };
    var caixa = tauler.getBoundingClientRect();
    var esquerra = Math.max(caixa.left, 0) + vora;
    var dreta = Math.min(caixa.right, window.innerWidth) - vora;
    if (drag.x < esquerra) {
      tauler.scrollLeft -= velocitat(esquerra - drag.x);
    } else if (drag.x > dreta) {
      tauler.scrollLeft += velocitat(drag.x - dreta);
    }
    if (drag.y < vora) {
      window.scrollBy(0, -velocitat(vora - drag.y));
    } else if (drag.y > window.innerHeight - vora) {
      window.scrollBy(0, velocitat(drag.y - (window.innerHeight - vora)));
    }
    segueix();
    drag.frame = requestAnimationFrame(desplacaSol);
  }

  function aixeca(el, inici) {
    var caixa = el.getBoundingClientRect();
    // The copy keeps the card's place in the column while the card itself
    // is carried above everything else.
    var ombra = el.cloneNode(true);
    ombra.classList.remove("pressed");
    ombra.classList.add("drag-ghost");
    ombra.setAttribute("aria-hidden", "true");
    ombra.removeAttribute("data-spec");
    el.before(ombra);
    el.style.setProperty("left", caixa.left + "px");
    el.style.setProperty("top", caixa.top + "px");
    el.style.setProperty("width", caixa.width + "px");
    el.style.setProperty("height", caixa.height + "px");
    el.classList.add("lifted");
    document.body.classList.add("reordering");
    drag = {
      el: el,
      ombra: ombra,
      spec: el.dataset.spec,
      origen: el.dataset.estat,
      permesos: permesos(el),
      pointerId: inici.pointerId,
      x: inici.x,
      y: inici.y,
      startX: inici.x,
      startY: inici.y,
      desti: null,
      frame: null
    };
    try {
      el.setPointerCapture(inici.pointerId);
    } catch (error) {
      // A pointer the browser no longer knows: the drag simply never moves.
    }
    tauler.querySelectorAll(".column").forEach(function (columna) {
      if (drag.permesos.indexOf(columna.dataset.estat) !== -1) {
        columna.classList.add("drop-allowed");
      }
    });
    drag.frame = requestAnimationFrame(desplacaSol);
  }

  // Puts a carried card back in the flow of its column.
  function assenta(el, ombra) {
    if (ombra) {
      ombra.remove();
    }
    el.classList.remove("lifted", "returning");
    ["left", "top", "width", "height", "transform"].forEach(function (propietat) {
      el.style.removeProperty(propietat);
    });
  }

  // A cancelled or refused drop: the card glides back to the place it left.
  function tornaACasa(el, ombra) {
    if (!el.isConnected) {
      return;
    }
    el.classList.add("returning");
    el.style.setProperty("transform", "translate(0px, 0px)");
    setTimeout(function () {
      assenta(el, ombra);
    }, 170);
  }

  // The dropped card glides from where it was left to its place on the
  // board, settling back to its size on the way.
  function aterra(targeta, des) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !targeta.animate) {
      aterratge = Promise.resolve();
      return;
    }
    var aqui = centre(targeta);
    var dx = des.x - aqui.x;
    var dy = des.y - aqui.y;
    var estil = getComputedStyle(document.documentElement);
    targeta.classList.add("landing");
    // Longer for a longer way, within limits.
    var durada = Math.min(360, 180 + Math.hypot(dx, dy) / 4);
    var vol = targeta.animate(
      [
        { translate: dx + "px " + dy + "px", scale: "1.05", boxShadow: estil.getPropertyValue("--shadow-lg") },
        { translate: "0px 0px", scale: "1", boxShadow: estil.getPropertyValue("--shadow-sm") }
      ],
      { duration: durada, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)" }
    );
    var fet = function () { targeta.classList.remove("landing"); };
    vol.addEventListener("finish", fet);
    vol.addEventListener("cancel", fet);
    // A browser does not run animations in a tab that is not on screen, so
    // whatever waits for the glide also stops waiting after a moment.
    aterratge = Promise.race([
      vol.finished.catch(function () {}),
      new Promise(function (resol) { setTimeout(resol, durada + 200); })
    ]);
  }

  // A card dropped on "Bloquejat" first lands there, and only then is the
  // reason asked. Without a reason (or if the server refuses) the card
  // glides back to the place it came from.
  function bloquejaDespresDAterrar(el, ombra, spec, origen, des) {
    var columna = tauler.querySelector('.column[data-estat="bloquejat"]');
    var buit = columna.querySelector(".column-empty");
    provisional = true;
    assenta(el, null);
    ombra.hidden = true; // Still marks the place the card came from.
    if (buit) {
      buit.hidden = true;
    }
    el.classList.remove(origen);
    el.classList.add("bloquejat");
    columna.appendChild(el);
    aplicaFiltre();
    aterra(el, des);

    function desfes() {
      var ara = centre(el);
      el.classList.remove("bloquejat");
      el.classList.add(origen);
      ombra.before(el);
      ombra.remove();
      if (buit) {
        buit.hidden = false;
      }
      aplicaFiltre();
      aterra(el, ara);
    }

    aterratge
      .then(demanaMotiu)
      .then(function (motiu) {
        if (!motiu) {
          return false;
        }
        // On success the board is drawn again with the card already in place.
        return envia(spec, "mou", { estat: "bloquejat", motiu: motiu });
      })
      .then(function (fet) {
        provisional = false;
        if (!fet && el.isConnected) {
          desfes();
        }
      });
  }

  // Ends the drag. With a column to drop on, the task moves there; without
  // one (cancelled, or dropped where it cannot go) the card glides back.
  function deixa(confirma) {
    if (!drag) {
      return;
    }
    var el = drag.el;
    var ombra = drag.ombra;
    var spec = drag.spec;
    var origen = drag.origen;
    var desti = confirma ? drag.desti : null;
    cancelAnimationFrame(drag.frame);
    drag = null;
    document.body.classList.remove("reordering");
    tauler.querySelectorAll(".drop-ok, .drop-allowed").forEach(function (columna) {
      columna.classList.remove("drop-ok", "drop-allowed");
    });
    // The click that ends a drag must not open the task.
    var empassa = function (event) {
      event.stopPropagation();
      event.preventDefault();
    };
    window.addEventListener("click", empassa, { capture: true, once: true });
    setTimeout(function () {
      window.removeEventListener("click", empassa, { capture: true });
    }, 50);

    if (!desti) {
      tornaACasa(el, ombra);
      return;
    }
    var des = centre(el);
    if (desti === "bloquejat") {
      bloquejaDespresDAterrar(el, ombra, spec, origen, des);
      return;
    }
    // The card stays where it was dropped, still lifted, while the server is
    // asked. When the board is drawn again it glides from there to its place.
    aterrat = { spec: spec, x: des.x, y: des.y };
    envia(spec, "mou", { estat: desti }).then(function (fet) {
      if (!fet) {
        aterrat = null;
        tornaACasa(el, ombra);
      }
    });
  }

  function oblida() {
    if (pendent) {
      clearTimeout(pendent.timer);
      pendent.el.classList.remove("pressed");
    }
    pendent = null;
  }

  function aixecaPendent() {
    var inici = pendent;
    oblida();
    if (inici.el.isConnected) {
      aixeca(inici.el, inici);
    }
  }

  tauler.addEventListener("pointerdown", function (event) {
    if (drag || pendent || provisional || (event.pointerType === "mouse" && event.button !== 0)) {
      return;
    }
    var el = event.target.closest(".task-card.can-drag");
    // The "Mou a…" list keeps working as a list.
    if (!el || event.target.closest("select, a")) {
      return;
    }
    pendent = {
      el: el,
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      touch: event.pointerType !== "mouse",
      timer: null
    };
    // With a mouse the card lifts as soon as it is pressed. A finger has to
    // wait for the long press: lifting at once would make every scroll flash
    // the cards.
    if (!pendent.touch) {
      el.classList.add("pressed");
    } else {
      pendent.timer = setTimeout(function () {
        if (navigator.vibrate) {
          navigator.vibrate(15);
        }
        aixecaPendent();
      }, LONG_PRESS_MS);
    }
  });

  // While a card is carried by a finger the page must not scroll under it,
  // and a long press must not open the system menu.
  tauler.addEventListener("touchmove", function (event) {
    if (drag && event.cancelable) {
      event.preventDefault();
    }
  }, { passive: false });
  tauler.addEventListener("contextmenu", function (event) {
    if (pendent || drag) {
      event.preventDefault();
    }
  });

  // The rest of the gesture is followed on the whole page: a quick pull takes
  // the pointer off the card before it has lifted.
  document.addEventListener("pointermove", function (event) {
    if (drag && event.pointerId === drag.pointerId) {
      drag.x = event.clientX;
      drag.y = event.clientY;
      segueix();
      return;
    }
    if (!pendent || event.pointerId !== pendent.pointerId) {
      return;
    }
    var mogut = Math.hypot(event.clientX - pendent.x, event.clientY - pendent.y);
    if (pendent.touch) {
      // A swipe: the browser scrolls, and this press is not a drag.
      if (mogut > SLOP_PX) {
        oblida();
      }
    } else if (mogut > PULL_PX) {
      aixecaPendent();
      if (drag) {
        drag.x = event.clientX;
        drag.y = event.clientY;
        segueix();
      }
    }
  });

  function fiPunter(event) {
    if (pendent && event.pointerId === pendent.pointerId) {
      oblida();
    }
    if (drag && event.pointerId === drag.pointerId) {
      deixa(event.type === "pointerup");
    }
  }
  document.addEventListener("pointerup", fiPunter);
  document.addEventListener("pointercancel", fiPunter);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && drag) {
      deixa(false);
    }
  });

  // ---- Task dialog --------------------------------------------------------

  function mostraPestanya(nom) {
    if (!contingut.querySelector('[data-panel="' + nom + '"]')) {
      nom = "descripcio";
    }
    pestanya = nom;
    contingut.querySelectorAll("[data-tab]").forEach(function (boto) {
      boto.setAttribute("aria-selected", boto.dataset.tab === nom ? "true" : "false");
    });
    contingut.querySelectorAll("[data-panel]").forEach(function (panell) {
      panell.hidden = panell.dataset.panel !== nom;
    });
  }

  function carregaTasca(spec) {
    return fetch(base + "/tasques/" + spec)
      .then(function (resposta) {
        if (!resposta.ok) {
          throw new Error();
        }
        return resposta.text();
      })
      .then(function (html) {
        contingut.innerHTML = html;
        mostraPestanya(pestanya);
        aplicaEdicio();
      })
      .catch(function () {
        UI.toast("No s'ha pogut obrir la tasca.", "error");
      });
  }

  tauler.addEventListener("click", function (event) {
    var boto = event.target.closest("[data-obre-tasca]");
    if (!boto) {
      return;
    }
    specOberta = boto.dataset.obreTasca;
    pestanya = "descripcio";
    carregaTasca(specOberta).then(function () {
      UI.openModal(modalTasca, function () {
        specOberta = null;
        contingut.innerHTML = "";
      });
    });
  });

  contingut.addEventListener("click", function (event) {
    var tab = event.target.closest("[data-tab]");
    if (tab) {
      mostraPestanya(tab.dataset.tab);
      return;
    }
    var boto = event.target.closest("[data-mou-estat]");
    if (boto && specOberta !== null) {
      mou(specOberta, boto.dataset.mouEstat);
    }
  });

  contingut.addEventListener("submit", function (event) {
    var form = event.target.closest("form[data-accio]");
    if (!form || specOberta === null) {
      return;
    }
    event.preventDefault();
    var camps = {};
    new FormData(form).forEach(function (valor, clau) {
      camps[clau] = valor;
    });
    var boto = form.querySelector('[type="submit"]');
    if (boto) {
      boto.disabled = true;
    }
    envia(specOberta, form.dataset.accio, camps).then(function () {
      if (boto) {
        boto.disabled = false;
      }
    });
  });

  // ---- Filter, teacher switch, automatic refresh ---------------------------

  if (filtre) {
    try {
      filtre.value = sessionStorage.getItem("tauler-sprint:" + base) || "";
    } catch (error) { /* storage may be unavailable */ }
    filtre.addEventListener("change", function () {
      try {
        sessionStorage.setItem("tauler-sprint:" + base, filtre.value);
      } catch (error) { /* ignore */ }
      aplicaFiltre();
    });
  }
  if (edicio) {
    edicio.addEventListener("change", aplicaEdicio);
  }

  aplicaEdicio();
  aplicaFiltre();

  // Ask the server whether anything changed; repaint only when it did, and
  // never under the user's hands (while dragging or with a dialog open).
  if (interval > 0) {
    setInterval(function () {
      if (document.hidden || ocupat() || modalMotiu.open) {
        return;
      }
      fetch(base + "/versio")
        .then(function (resposta) { return resposta.json(); })
        .then(function (dades) {
          if (dades.versio === versio) {
            return;
          }
          refresca().then(function () {
            if (specOberta !== null && !contingut.contains(document.activeElement)) {
              carregaTasca(specOberta);
            }
          });
        })
        .catch(function () {});
    }, interval * 1000);
  }
})();
