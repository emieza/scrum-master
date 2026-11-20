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
  var arrossegant = false;
  var motiuPendent = null;

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
      targeta.draggable = edicioActiva();
    });
  }

  function aplicaFiltre() {
    var valor = filtre ? filtre.value : "";
    tauler.querySelectorAll(".task-card").forEach(function (targeta) {
      var sprints = targeta.dataset.sprints ? targeta.dataset.sprints.split(",") : [];
      var visible =
        !valor ||
        (valor === "backlog" ? sprints.length === 0 : sprints.indexOf(valor) !== -1);
      targeta.hidden = !visible;
    });
    tauler.querySelectorAll(".column").forEach(function (columna) {
      var visibles = columna.querySelectorAll(".task-card:not([hidden])").length;
      columna.querySelector(".count").textContent = visibles;
    });
  }

  function pinta(dades) {
    tauler.innerHTML = dades.html;
    versio = dades.versio;
    aplicaEdicio();
    aplicaFiltre();
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

  function mou(spec, estat) {
    if (!estat) {
      return;
    }
    if (estat === "bloquejat") {
      // Blocking always asks why.
      motiuPendent = spec;
      motiuText.value = "";
      UI.openModal(modalMotiu);
      motiuText.focus();
      return;
    }
    envia(spec, "mou", { estat: estat });
  }

  formMotiu.addEventListener("submit", function (event) {
    event.preventDefault();
    var motiu = motiuText.value.trim();
    if (!motiu || motiuPendent === null) {
      return;
    }
    var spec = motiuPendent;
    motiuPendent = null;
    UI.closeModal(modalMotiu);
    envia(spec, "mou", { estat: "bloquejat", motiu: motiu });
  });

  tauler.addEventListener("change", function (event) {
    var select = event.target.closest("[data-mou]");
    if (!select) {
      return;
    }
    var estat = select.value;
    select.value = "";
    mou(select.dataset.mou, estat);
  });

  tauler.addEventListener("dragstart", function (event) {
    var targeta = event.target.closest(".task-card");
    if (!targeta || !edicioActiva()) {
      event.preventDefault();
      return;
    }
    arrossegant = true;
    targeta.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", targeta.dataset.spec);
  });

  tauler.addEventListener("dragend", function (event) {
    arrossegant = false;
    var targeta = event.target.closest(".task-card");
    if (targeta) {
      targeta.classList.remove("dragging");
    }
    tauler.querySelectorAll(".drop-ok").forEach(function (columna) {
      columna.classList.remove("drop-ok");
    });
  });

  tauler.addEventListener("dragover", function (event) {
    var columna = event.target.closest(".column");
    if (!columna || !arrossegant) {
      return;
    }
    event.preventDefault();
    tauler.querySelectorAll(".drop-ok").forEach(function (altra) {
      if (altra !== columna) {
        altra.classList.remove("drop-ok");
      }
    });
    columna.classList.add("drop-ok");
  });

  tauler.addEventListener("drop", function (event) {
    var columna = event.target.closest(".column");
    if (!columna) {
      return;
    }
    event.preventDefault();
    var spec = event.dataTransfer.getData("text/plain");
    var targeta = tauler.querySelector('.task-card[data-spec="' + spec + '"]');
    if (targeta && targeta.dataset.estat !== columna.dataset.estat) {
      mou(spec, columna.dataset.estat);
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
      if (document.hidden || arrossegant || modalMotiu.open) {
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
