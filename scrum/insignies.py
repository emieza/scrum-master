"""Insígnies de treball en equip del tauler Kanban.

Qualsevol equip pot aconseguir totes les insígnies: premien com es reparteix
la feina, no qui va més de pressa. Cada insígnia és una proporció sobre tot el
que l'equip ha finalitzat fins ara, de manera que es pot perdre si l'equip
deixa de treballar així.

El mèrit d'una tasca finalitzada és de la persona responsable, no de qui l'ha
passada a «Finalitzat». Només compten les persones que són a l'equip ara.
"""

import math

from .kanban import FINALITZAT

# Fins on es pot allunyar una persona d'un repartiment a parts iguals: un 15%,
# i mai menys d'una tasca (o de les hores d'una tasca mitjana), perquè les
# tasques són senceres i els equips petits.
MARGE = 0.15
MIN_COBERTURA_MODULS = 0.5  # dels mòduls que ha treballat l'equip
MIN_SOLITARI = 1 / 3  # de les tasques pròpies de cada persona
MIN_MODULS_PROJECTE = 2
MIN_MEMBRES_REVISIO = 3

DEFINICIONS = [
    {
        "clau": "tothom_tasques",
        "icona": "🙌",
        "nom": "Tothom treballa · tasques",
        "com": (
            "Ningú no ha finalitzat menys tasques de les que li tocarien a "
            "parts iguals, amb un marge del 15% (com a mínim, d'una tasca). "
            "Tothom en té almenys una."
        ),
    },
    {
        "clau": "tothom_hores",
        "icona": "⏱️",
        "nom": "Tothom treballa · hores",
        "com": (
            "Com l'anterior, però comptant les hores estimades de les tasques "
            "en lloc del nombre de tasques."
        ),
    },
    {
        "clau": "repartida_tasques",
        "icona": "⚖️",
        "nom": "Feina ben repartida · tasques",
        "com": (
            "Ningú no ha finalitzat més tasques de les que li tocarien a "
            "parts iguals, amb un marge del 15% (com a mínim, d'una tasca)."
        ),
    },
    {
        "clau": "repartida_hores",
        "icona": "🧮",
        "nom": "Feina ben repartida · hores",
        "com": (
            "Com l'anterior, però comptant les hores estimades de les tasques "
            "en lloc del nombre de tasques."
        ),
    },
    {
        "clau": "polivalents",
        "icona": "🧩",
        "nom": "Polivalents",
        "com": (
            "Cada persona ha finalitzat tasques de, com a mínim, la meitat "
            "dels mòduls professionals que ha treballat l'equip."
        ),
    },
    {
        "clau": "autonomia",
        "icona": "🧭",
        "nom": "Autonomia",
        "com": (
            "Cada persona ha finalitzat pel seu compte, sense col·laboradors, "
            "almenys un terç de les seves tasques."
        ),
    },
    {
        "clau": "tothom_revisa",
        "icona": "🔍",
        "nom": "Tothom revisa",
        "com": (
            "Cada persona ha validat (de «Test» a «Finalitzat») la part que li "
            "toca de les tasques dels companys, amb un marge del 15% (com a "
            "mínim, d'una tasca)."
        ),
    },
]

NO_DISPONIBLE = {
    "equip": "Només per a equips de dues persones o més.",
    "equip_revisio": "Només per a equips de tres persones o més.",
    "moduls": "El projecte necessita almenys dos mòduls professionals.",
    "hores": "Les tasques del projecte no tenen hores estimades.",
}


def _tasques(n):
    return "{} {}".format(n, "tasca" if n == 1 else "tasques")


def _hores(valor):
    return "{:g} h".format(round(valor, 1))


def _percent(fraccio):
    return "{}%".format(round(fraccio * 100))


def calcula(membres, finalitzades, moduls_projecte, hores_projecte):
    """Insígnies d'un equip.

    ``membres``: ids de les persones que són a l'equip ara.
    ``finalitzades``: una entrada per tasca finalitzada, amb ``responsable``
    (id), ``validada_per`` (id o None), ``hores``, ``moduls`` (conjunt d'ids)
    i ``sola`` (sense col·laboradors).
    """
    ids = list(membres)
    mida = len(ids)
    # Només compta la feina de qui és a l'equip ara.
    propies = [t for t in finalitzades if t["responsable"] in membres]

    per_persona = {
        pk: {"n": 0, "hores": 0.0, "soles": 0, "moduls": set(), "validades": 0, "validables": 0}
        for pk in ids
    }
    for tasca in propies:
        dades = per_persona[tasca["responsable"]]
        dades["n"] += 1
        dades["hores"] += tasca["hores"]
        dades["soles"] += 1 if tasca["sola"] else 0
        dades["moduls"] |= tasca["moduls"]
        # Validacions fetes per membres: les del professorat no compten.
        if tasca["validada_per"] in membres:
            per_persona[tasca["validada_per"]]["validades"] += 1
            for pk in ids:
                if pk != tasca["responsable"]:
                    per_persona[pk]["validables"] += 1

    total = len(propies)
    total_hores = sum(t["hores"] for t in propies)
    moduls_equip = set().union(*(d["moduls"] for d in per_persona.values())) if ids else set()

    # Tot es mesura quan hi ha, de mitjana, una tasca finalitzada per persona.
    prou = mida > 0 and total >= mida
    espera = "Encara no compta: {} de {} tasques finalitzades".format(total, mida)

    def mesura(aconseguida, progres):
        if not prou:
            return {"aconseguida": False, "progres": espera}
        return {"aconseguida": bool(aconseguida), "progres": progres}

    def minim(valors):
        return min(valors) if valors else 0

    def maxim(valors):
        return max(valors) if valors else 0

    # Tasques: 12 tasques entre 3 persones en són 4 per cap, i entre 3 i 5 val.
    comptes = [per_persona[pk]["n"] for pk in ids]
    igual = total / mida if mida else 0
    marge = max(1, igual * MARGE)
    menys = max(1, math.ceil(igual - marge))
    mes = math.floor(igual + marge)

    # Hores: el mateix, amb les hores d'una tasca mitjana com a marge mínim.
    hores = [per_persona[pk]["hores"] for pk in ids]
    igual_h = total_hores / mida if mida else 0
    marge_h = max(total_hores / total if total else 0, igual_h * MARGE)
    menys_h = max(0.0, igual_h - marge_h)
    mes_h = igual_h + marge_h

    cobertura = [
        len(per_persona[pk]["moduls"]) / len(moduls_equip) if moduls_equip else 0
        for pk in ids
    ]
    solitari = [
        per_persona[pk]["soles"] / per_persona[pk]["n"] if per_persona[pk]["n"] else 0
        for pk in ids
    ]

    # Revisions: cadascú, la part que li toca de les tasques que podia validar
    # (les dels altres), perquè ningú no pot validar les seves.
    revisio_ok = True
    pitjor = None
    for pk in ids:
        dades = per_persona[pk]
        toca = dades["validables"] / (mida - 1) if mida > 1 else 0
        cal = max(1, math.ceil(toca - max(1, toca * MARGE))) if dades["validables"] else 0
        if dades["validades"] < cal:
            revisio_ok = False
        if pitjor is None or dades["validades"] - cal < pitjor[0] - pitjor[1]:
            pitjor = (dades["validades"], cal)
    pitjor = pitjor or (0, 0)

    resultats = {
        "tothom_tasques": mesura(
            minim(comptes) >= menys,
            "Qui menys: {} (mínim {})".format(_tasques(minim(comptes)), menys),
        ),
        "tothom_hores": mesura(
            minim(hores) > 0 and minim(hores) >= menys_h,
            "Qui menys: {} (mínim {})".format(_hores(minim(hores)), _hores(menys_h)),
        ),
        "repartida_tasques": mesura(
            maxim(comptes) <= mes,
            "Qui més: {} (màxim {})".format(_tasques(maxim(comptes)), mes),
        ),
        "repartida_hores": mesura(
            maxim(hores) <= mes_h,
            "Qui més: {} (màxim {})".format(_hores(maxim(hores)), _hores(mes_h)),
        ),
        "polivalents": mesura(
            bool(moduls_equip) and minim(cobertura) >= MIN_COBERTURA_MODULS,
            "Qui menys: {} dels mòduls (cal {})".format(
                _percent(minim(cobertura)), _percent(MIN_COBERTURA_MODULS)
            ),
        ),
        "autonomia": mesura(
            minim(solitari) >= MIN_SOLITARI,
            "Qui menys: {} en solitari (cal {})".format(
                _percent(minim(solitari)), _percent(MIN_SOLITARI)
            ),
        ),
        "tothom_revisa": mesura(
            revisio_ok,
            "Qui menys: {} (mínim {})".format(
                "{} {}".format(pitjor[0], "validació" if pitjor[0] == 1 else "validacions"),
                pitjor[1],
            ),
        ),
    }

    no_disponible = {}
    if mida < 2:
        no_disponible["repartida_tasques"] = "equip"
        no_disponible["repartida_hores"] = "equip"
    if mida < MIN_MEMBRES_REVISIO:
        no_disponible["tothom_revisa"] = "equip_revisio" if mida >= 2 else "equip"
    if moduls_projecte < MIN_MODULS_PROJECTE:
        no_disponible["polivalents"] = "moduls"
    if not hores_projecte:
        no_disponible.setdefault("tothom_hores", "hores")
        no_disponible["repartida_hores"] = no_disponible.get("repartida_hores", "hores")

    llista = []
    for definicio in DEFINICIONS:
        insignia = dict(definicio)
        motiu = no_disponible.get(definicio["clau"])
        if motiu:
            insignia.update(
                aconseguida=False, progres="", no_disponible=NO_DISPONIBLE[motiu]
            )
        else:
            insignia.update(resultats[definicio["clau"]], no_disponible="")
        llista.append(insignia)
    return llista


def de_l_equip(equip, moduls_projecte=None, hores_projecte=None):
    """Llegeix de la base de dades el que cal i calcula les insígnies."""
    projecte = equip.projecte
    if moduls_projecte is None:
        moduls_projecte = len(projecte.mps())
    if hores_projecte is None:
        hores_projecte = sum(
            projecte.specs.values_list("hores_estimades", flat=True)
        )
    membres = set(equip.membres.values_list("pk", flat=True))
    finalitzades = [
        {
            "responsable": tasca.responsable_id,
            "validada_per": tasca.validada_per_id,
            "hores": tasca.spec.hores_estimades or 0.0,
            "moduls": {mp.pk for mp in tasca.spec.mp.all()},
            "sola": not tasca.colaboradors.all(),
        }
        for tasca in equip.tasques.filter(
            estat=FINALITZAT, spec__projecte=equip.projecte_id
        )
        .select_related("spec")
        .prefetch_related("spec__mp", "colaboradors")
    ]
    return calcula(membres, finalitzades, moduls_projecte, hores_projecte)
