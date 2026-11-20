"""Regles del tauler Kanban dels equips.

Tot el que decideix qui pot fer què amb una tasca és aquí, i les vistes només
tradueixen peticions HTTP a aquestes funcions. Cada canvi afegeix una fila a
l'historial (``TascaEvent``), que també serveix per saber si un tauler obert
s'ha de refrescar.
"""

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from .models import (
    DoneSpec,
    TascaBloqueig,
    TascaComentari,
    TascaEquip,
    TascaEvent,
)

PENDENT = TascaEquip.PENDENT
EN_CURS = TascaEquip.EN_CURS
BLOQUEJAT = TascaEquip.BLOQUEJAT
TEST = TascaEquip.TEST
FINALITZAT = TascaEquip.FINALITZAT

# Ordre de les columnes del tauler.
ESTATS = [PENDENT, EN_CURS, BLOQUEJAT, TEST, FINALITZAT]
NOMS_ESTAT = dict(TascaEquip.ESTATS)

# Qui mira el tauler.
PROFE = "profe"  # professorat del projecte i administració: ho pot tot
MEMBRE = "membre"  # alumnat de l'equip
PUBLIC = "public"  # tothom altre: tauler sense noms ni textos

# Canvis d'estat permesos a l'alumnat. Des de «Bloquejat» només es pot tornar
# a l'estat d'on venia la tasca (vegeu ``transicions``).
_TRANSICIONS_MEMBRE = {
    PENDENT: [EN_CURS],
    EN_CURS: [TEST, BLOQUEJAT, PENDENT],
    TEST: [FINALITZAT, EN_CURS, BLOQUEJAT],
    FINALITZAT: [EN_CURS],
}


class ErrorKanban(Exception):
    """Acció no permesa; el missatge es mostra a l'usuari."""


def rol(usuari, equip):
    if usuari.is_authenticated:
        if usuari.is_superuser or equip.projecte.admins.filter(pk=usuari.pk).exists():
            return PROFE
        if equip.membres.filter(pk=usuari.pk).exists():
            return MEMBRE
    return PUBLIC


def transicions(tasca, rol_usuari):
    """Estats als quals ``rol_usuari`` pot moure la tasca."""
    if rol_usuari == PROFE:
        return [estat for estat in ESTATS if estat != tasca.estat]
    if rol_usuari != MEMBRE:
        return []
    if tasca.estat == BLOQUEJAT:
        return [tasca.estat_abans_bloqueig or EN_CURS]
    return _TRANSICIONS_MEMBRE[tasca.estat]


def versio(equip):
    """Canvia cada cop que passa alguna cosa al tauler de l'equip."""
    return (
        TascaEvent.objects.filter(tasca__equip=equip).aggregate(v=Max("id"))["v"]
        or 0
    )


def obte_tasca(equip, spec, bloqueja=False):
    """La tasca de l'equip per a la spec; la crea com a «Pendent» si cal."""
    tasca, _ = TascaEquip.objects.get_or_create(equip=equip, spec=spec)
    if bloqueja:
        tasca = TascaEquip.objects.select_for_update().get(pk=tasca.pk)
    return tasca


def _event(tasca, usuari, tipus, **camps):
    return TascaEvent.objects.create(
        tasca=tasca, usuari=usuari, tipus=tipus, **camps
    )


def _ids_membres(equip):
    return set(equip.membres.values_list("pk", flat=True))


@transaction.atomic
def neteja_exmembres(equip):
    """Deixa sense responsable les tasques obertes de qui ja no és a l'equip.

    Les tasques finalitzades conserven qui les va fer, però les insígnies
    només compten les persones que formen part de l'equip ara.
    """
    ids = _ids_membres(equip)
    orfes = (
        equip.tasques.exclude(estat=FINALITZAT)
        .exclude(responsable__isnull=True)
        .exclude(responsable_id__in=ids)
    )
    for tasca in orfes.select_related("responsable"):
        antic = tasca.responsable
        tasca.responsable = None
        tasca.save(update_fields=["responsable"])
        tasca.colaboradors.clear()
        _event(
            tasca,
            None,
            TascaEvent.RESPONSABLE,
            text="{} ja no forma part de l'equip: la tasca queda sense responsable.".format(
                antic.nom_complert or antic.email
            ),
        )
    for tasca in equip.tasques.exclude(estat=FINALITZAT).filter(
        colaboradors__isnull=False
    ).distinct():
        for persona in tasca.colaboradors.exclude(pk__in=ids):
            tasca.colaboradors.remove(persona)


@transaction.atomic
def mou(equip, spec, usuari, rol_usuari, nou_estat, motiu=""):
    """Canvia l'estat d'una tasca aplicant totes les regles."""
    if rol_usuari not in (PROFE, MEMBRE):
        raise ErrorKanban("No tens permís per moure tasques d'aquest equip.")
    if nou_estat not in ESTATS:
        raise ErrorKanban("Estat desconegut.")

    tasca = obte_tasca(equip, spec, bloqueja=True)
    actual = tasca.estat
    if nou_estat == actual:
        raise ErrorKanban(
            "La tasca ja és a «{}».".format(NOMS_ESTAT[actual])
        )
    if nou_estat not in transicions(tasca, rol_usuari):
        raise ErrorKanban(
            "Una tasca a «{}» no pot passar a «{}».".format(
                NOMS_ESTAT[actual], NOMS_ESTAT[nou_estat]
            )
        )

    motiu = (motiu or "").strip()
    if nou_estat == BLOQUEJAT and not motiu:
        raise ErrorKanban("Cal explicar per què es bloqueja la tasca.")

    membres = _ids_membres(equip)
    es_membre = rol_usuari == MEMBRE

    # Qui comença o envia a Test una tasca sense responsable se la queda.
    if es_membre and tasca.responsable_id is None and nou_estat in (EN_CURS, TEST):
        tasca.responsable = usuari
        _event(
            tasca,
            usuari,
            TascaEvent.RESPONSABLE,
            afectat=usuari,
            text="ha quedat com a responsable automàticament",
        )

    # Desbloquejar una tasca que era a Test ho pot fer qualsevol membre.
    if (
        es_membre
        and nou_estat == TEST
        and actual != BLOQUEJAT
        and tasca.responsable_id != usuari.pk
    ):
        raise ErrorKanban(
            "Només la persona responsable pot enviar la tasca a «Test»."
        )

    # De Test a Finalitzat ho valida una altra persona de l'equip, tret que
    # l'equip sigui d'una sola persona.
    if es_membre and actual == TEST and nou_estat == FINALITZAT and len(membres) > 1:
        if usuari.pk in (tasca.responsable_id, tasca.enviada_a_test_per_id):
            raise ErrorKanban(
                "No pots validar una tasca teva: l'ha de passar a "
                "«Finalitzat» una altra persona de l'equip."
            )

    if actual == BLOQUEJAT:
        tasca.bloquejos.filter(tancat_el__isnull=True).update(
            tancat_per=usuari, tancat_el=timezone.now()
        )
        tasca.estat_abans_bloqueig = ""
    if nou_estat == BLOQUEJAT:
        tasca.estat_abans_bloqueig = actual
        TascaBloqueig.objects.create(tasca=tasca, motiu=motiu, obert_per=usuari)

    # Qui ha enviat la tasca a Test es conserva mentre la tasca és a Test,
    # encara que entremig s'hagi bloquejat i desbloquejat.
    if nou_estat == TEST and actual != BLOQUEJAT:
        tasca.enviada_a_test_per = usuari
    elif nou_estat not in (TEST, BLOQUEJAT):
        tasca.enviada_a_test_per = None

    if nou_estat == FINALITZAT:
        tasca.finalitzada_el = timezone.now()
        tasca.validada_per = usuari
    else:
        tasca.finalitzada_el = None
        tasca.validada_per = None

    tasca.estat = nou_estat
    tasca.save()
    _event(
        tasca,
        usuari,
        TascaEvent.ESTAT,
        estat_origen=actual,
        estat_desti=nou_estat,
        text=motiu if nou_estat == BLOQUEJAT else "",
    )
    return tasca


@transaction.atomic
def canvia_responsable(equip, spec, usuari, rol_usuari, nou):
    """Traspassa la tasca. ``nou`` és un usuari o ``None`` (només professorat)."""
    if rol_usuari not in (PROFE, MEMBRE):
        raise ErrorKanban("No tens permís per canviar la persona responsable.")
    tasca = obte_tasca(equip, spec, bloqueja=True)
    membres = _ids_membres(equip)

    if nou is not None and nou.pk not in membres:
        raise ErrorKanban("La persona responsable ha de ser membre de l'equip.")
    if nou is None and rol_usuari != PROFE:
        raise ErrorKanban("Només el professorat pot deixar una tasca sense responsable.")
    if (nou.pk if nou else None) == tasca.responsable_id:
        raise ErrorKanban("Aquesta persona ja és la responsable de la tasca.")

    if rol_usuari == MEMBRE:
        if tasca.responsable_id is None:
            if nou.pk != usuari.pk:
                raise ErrorKanban("Una tasca sense responsable només la pots assumir tu.")
        elif tasca.responsable_id != usuari.pk:
            raise ErrorKanban("Només la persona responsable pot traspassar la tasca.")
        elif tasca.estat == TEST:
            raise ErrorKanban(
                "Una tasca a «Test» no es pot traspassar: abans ha de tornar a «En curs»."
            )

    tasca.responsable = nou
    tasca.save(update_fields=["responsable"])
    if nou is None:
        tasca.colaboradors.clear()
    else:
        tasca.colaboradors.remove(nou)
    _event(tasca, usuari, TascaEvent.RESPONSABLE, afectat=nou)
    return tasca


@transaction.atomic
def canvia_colaborador(equip, spec, usuari, rol_usuari, persona, afegeix):
    tasca = obte_tasca(equip, spec, bloqueja=True)
    if rol_usuari == MEMBRE and tasca.responsable_id != usuari.pk:
        raise ErrorKanban("Només la persona responsable gestiona els col·laboradors.")
    if rol_usuari not in (PROFE, MEMBRE):
        raise ErrorKanban("No tens permís per gestionar els col·laboradors.")
    if tasca.responsable_id is None:
        raise ErrorKanban("Una tasca sense responsable no pot tenir col·laboradors.")

    if afegeix:
        if persona.pk not in _ids_membres(equip):
            raise ErrorKanban("Els col·laboradors han de ser membres de l'equip.")
        if persona.pk == tasca.responsable_id:
            raise ErrorKanban("La persona responsable no pot ser col·laboradora.")
        if tasca.colaboradors.filter(pk=persona.pk).exists():
            raise ErrorKanban("Aquesta persona ja hi col·labora.")
        tasca.colaboradors.add(persona)
        _event(tasca, usuari, TascaEvent.COLABORADOR_AFEGIT, afectat=persona)
    else:
        if not tasca.colaboradors.filter(pk=persona.pk).exists():
            raise ErrorKanban("Aquesta persona no hi col·labora.")
        tasca.colaboradors.remove(persona)
        _event(tasca, usuari, TascaEvent.COLABORADOR_TRET, afectat=persona)
    return tasca


@transaction.atomic
def comenta(equip, spec, usuari, rol_usuari, text):
    if rol_usuari not in (PROFE, MEMBRE):
        raise ErrorKanban("No tens permís per comentar aquesta tasca.")
    text = (text or "").strip()
    if not text:
        raise ErrorKanban("El comentari no pot estar buit.")
    tasca = obte_tasca(equip, spec, bloqueja=True)
    comentari = TascaComentari.objects.create(tasca=tasca, autor=usuari, text=text)
    _event(tasca, usuari, TascaEvent.COMENTARI)
    return comentari


# ---- Dades per pintar el tauler ---------------------------------------------


def _percentatges_qualificats(equip):
    """Percentatge que el professorat ha posat a cada spec (darrer sprint)."""
    resultat = {}
    done_specs = DoneSpec.objects.filter(qualificacio__equip=equip).order_by(
        "qualificacio__sprint__inici", "qualificacio__sprint__id"
    )
    for done in done_specs:
        resultat[done.spec_id] = done.percentatge
    return resultat


def dades_tauler(equip, rol_usuari):
    """Columnes del tauler amb les seves targetes, a punt per a la plantilla."""
    neteja_exmembres(equip)
    public = rol_usuari == PUBLIC
    specs = list(
        equip.projecte.specs.order_by("ordre", "id").prefetch_related("mp", "sprints")
    )
    tasques = {
        tasca.spec_id: tasca
        for tasca in equip.tasques.select_related("responsable")
        .prefetch_related("colaboradors")
        .annotate(n_comentaris=Count("comentaris", distinct=True))
    }
    motius = {
        bloqueig.tasca_id: bloqueig.motiu
        for bloqueig in TascaBloqueig.objects.filter(
            tasca__equip=equip, tancat_el__isnull=True
        )
    }
    qualificats = {} if public else _percentatges_qualificats(equip)

    columnes = {estat: [] for estat in ESTATS}
    for spec in specs:
        tasca = tasques.get(spec.id) or TascaEquip(equip=equip, spec=spec)
        sprints = list(spec.sprints.all())
        targeta = {
            "spec": spec,
            "estat": tasca.estat,
            "moduls": list(spec.mp.all()),
            "sprints": sprints,
            "sprint_ids": ",".join(str(sprint.id) for sprint in sprints),
            "transicions": [
                (estat, NOMS_ESTAT[estat]) for estat in transicions(tasca, rol_usuari)
            ],
            "finalitzada_el": tasca.finalitzada_el,
        }
        if not public:
            targeta.update(
                responsable=tasca.responsable,
                colaboradors=list(tasca.colaboradors.all()) if tasca.pk else [],
                n_comentaris=getattr(tasca, "n_comentaris", 0),
                motiu=motius.get(tasca.pk, ""),
                qualificat=qualificats.get(spec.id),
            )
        columnes[tasca.estat].append(targeta)

    # «Finalitzat» és un historial: en l'ordre en què s'han acabat.
    columnes[FINALITZAT].sort(
        key=lambda targeta: (targeta["finalitzada_el"] is None, targeta["finalitzada_el"])
    )
    return [
        {"estat": estat, "nom": NOMS_ESTAT[estat], "targetes": columnes[estat]}
        for estat in ESTATS
    ]


def progres(equip, total_specs=None):
    """Nombre de tasques de l'equip a cada estat i percentatge finalitzat."""
    if total_specs is None:
        total_specs = equip.projecte.specs.count()
    comptes = {estat: 0 for estat in ESTATS}
    del_projecte = equip.tasques.filter(spec__projecte=equip.projecte_id)
    for fila in del_projecte.values("estat").annotate(n=Count("id")):
        comptes[fila["estat"]] = fila["n"]
    comptes[PENDENT] = max(0, total_specs - sum(comptes[e] for e in ESTATS if e != PENDENT))
    percentatges = {
        estat: (comptes[estat] * 100 / total_specs if total_specs else 0)
        for estat in ESTATS
    }
    return {
        "comptes": comptes,
        "percentatges": percentatges,
        "total": total_specs,
        "percent": round(percentatges[FINALITZAT]),
        "barres": [
            {"estat": estat, "nom": NOMS_ESTAT[estat], "n": comptes[estat], "ample": percentatges[estat]}
            for estat in ESTATS
        ],
    }
