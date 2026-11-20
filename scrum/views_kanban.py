"""Vistes del tauler Kanban dels equips.

Les regles són a ``kanban.py`` i ``insignies.py``; aquí només hi ha permisos
d'accés a cada pantalla i la traducció entre HTTP i aquelles funcions.
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import insignies, kanban
from .models import (
    Equip,
    Projecte,
    Spec,
    TascaBloqueig,
    TascaEquip,
    User,
)


def _equip(equip_id):
    return get_object_or_404(
        Equip.objects.select_related("projecte"), pk=equip_id
    )


def _spec(equip, spec_id):
    return get_object_or_404(Spec, pk=spec_id, projecte=equip.projecte_id)


def _pot_gestionar(usuari, projecte):
    return usuari.is_authenticated and (
        usuari.is_superuser or projecte.admins.filter(pk=usuari.pk).exists()
    )


def _pot_veure_insignies(usuari, projecte):
    """Professorat sempre; alumnat del projecte si el projecte les mostra."""
    if _pot_gestionar(usuari, projecte):
        return True
    return (
        usuari.is_authenticated
        and projecte.insignies_visibles
        and projecte.equips.filter(membres=usuari).exists()
    )


def _context_columnes(equip, rol):
    return {
        "equip": equip,
        "rol": rol,
        "public": rol == kanban.PUBLIC,
        "pot_editar": rol in (kanban.PROFE, kanban.MEMBRE),
        "columnes": kanban.dades_tauler(equip, rol),
    }


def _resposta_tauler(request, equip, rol, **extra):
    """Columnes repintades i versió nova, després d'una acció."""
    html = render_to_string(
        "scrum/_tauler_columnes.html", _context_columnes(equip, rol), request=request
    )
    return JsonResponse(
        {"ok": True, "html": html, "versio": kanban.versio(equip), **extra}
    )


def _error(missatge, status=400):
    return JsonResponse({"ok": False, "error": missatge}, status=status)


# ---- Tauler -------------------------------------------------------------------


def tauler(request, equip_id):
    equip = _equip(equip_id)
    rol = kanban.rol(request.user, equip)
    context = _context_columnes(equip, rol)
    context.update(
        projecte=equip.projecte,
        membres=[] if rol == kanban.PUBLIC else list(equip.membres.order_by("first_name", "email")),
        sprints=list(equip.projecte.sprints.order_by("inici", "id")),
        versio=kanban.versio(equip),
        interval=settings.KANBAN_POLL_SECONDS,
        es_profe=rol == kanban.PROFE,
        mostra_insignies=_pot_veure_insignies(request.user, equip.projecte),
    )
    return render(request, "scrum/tauler.html", context)


def tauler_columnes(request, equip_id):
    equip = _equip(equip_id)
    return _resposta_tauler(request, equip, kanban.rol(request.user, equip))


def tauler_versio(request, equip_id):
    return JsonResponse({"versio": kanban.versio(_equip(equip_id))})


def tasca_detall(request, equip_id, spec_id):
    """Contingut del diàleg d'una tasca."""
    equip = _equip(equip_id)
    spec = _spec(equip, spec_id)
    rol = kanban.rol(request.user, equip)
    public = rol == kanban.PUBLIC
    tasca = (
        TascaEquip.objects.filter(equip=equip, spec=spec)
        .select_related("responsable")
        .first()
    ) or TascaEquip(equip=equip, spec=spec)

    context = {
        "equip": equip,
        "spec": spec,
        "tasca": tasca,
        "rol": rol,
        "public": public,
        "pot_editar": not public,
        "nom_estat": kanban.NOMS_ESTAT[tasca.estat],
        "moduls": list(spec.mp.all()),
        "sprints": list(spec.sprints.all()),
        "transicions": [
            (estat, kanban.NOMS_ESTAT[estat])
            for estat in kanban.transicions(tasca, rol)
        ],
    }
    if not public:
        membres = list(equip.membres.order_by("first_name", "email"))
        colaboradors = list(tasca.colaboradors.all()) if tasca.pk else []
        es_responsable = tasca.responsable_id == request.user.pk
        es_profe = rol == kanban.PROFE
        ocupats = {persona.pk for persona in colaboradors} | {tasca.responsable_id}
        context.update(
            membres=membres,
            colaboradors=colaboradors,
            comentaris=list(tasca.comentaris.select_related("autor")) if tasca.pk else [],
            bloquejos=list(
                tasca.bloquejos.select_related("obert_per", "tancat_per")
            ) if tasca.pk else [],
            events=list(
                tasca.events.select_related("usuari", "afectat").order_by("-creat_el", "-id")
            ) if tasca.pk else [],
            qualificat=kanban._percentatges_qualificats(equip).get(spec.id),
            es_profe=es_profe,
            # Traspassar: la persona responsable (no mentre és a Test) o el professorat.
            pot_traspassar=es_profe
            or (es_responsable and tasca.estat != kanban.TEST and len(membres) > 1),
            pot_assumir=rol == kanban.MEMBRE and tasca.responsable_id is None,
            pot_colaboradors=tasca.responsable_id is not None
            and (es_profe or es_responsable),
            candidats_responsable=[m for m in membres if m.pk != tasca.responsable_id],
            candidats_colaborador=[m for m in membres if m.pk not in ocupats],
        )
    return render(request, "scrum/_tasca_detall.html", context)


# ---- Accions sobre una tasca ----------------------------------------------------


def _accio(request, equip_id, spec_id):
    equip = _equip(equip_id)
    return equip, _spec(equip, spec_id), kanban.rol(request.user, equip)


def _membre(equip, valor):
    if not str(valor or "").isdigit():
        raise kanban.ErrorKanban("Tria una persona de l'equip.")
    persona = User.objects.filter(pk=valor).first()
    if persona is None:
        raise kanban.ErrorKanban("Tria una persona de l'equip.")
    return persona


@login_required
@require_POST
def tasca_mou(request, equip_id, spec_id):
    equip, spec, rol = _accio(request, equip_id, spec_id)
    try:
        kanban.mou(
            equip,
            spec,
            request.user,
            rol,
            request.POST.get("estat", ""),
            request.POST.get("motiu", ""),
        )
    except kanban.ErrorKanban as error:
        return _error(str(error))
    return _resposta_tauler(request, equip, rol)


@login_required
@require_POST
def tasca_responsable(request, equip_id, spec_id):
    equip, spec, rol = _accio(request, equip_id, spec_id)
    try:
        valor = request.POST.get("usuari", "")
        nou = None if valor == "" else _membre(equip, valor)
        kanban.canvia_responsable(equip, spec, request.user, rol, nou)
    except kanban.ErrorKanban as error:
        return _error(str(error))
    return _resposta_tauler(request, equip, rol)


@login_required
@require_POST
def tasca_colaborador(request, equip_id, spec_id):
    equip, spec, rol = _accio(request, equip_id, spec_id)
    try:
        persona = _membre(equip, request.POST.get("usuari", ""))
        kanban.canvia_colaborador(
            equip, spec, request.user, rol, persona,
            afegeix=request.POST.get("accio") != "treu",
        )
    except kanban.ErrorKanban as error:
        return _error(str(error))
    return _resposta_tauler(request, equip, rol)


@login_required
@require_POST
def tasca_comentari(request, equip_id, spec_id):
    equip, spec, rol = _accio(request, equip_id, spec_id)
    try:
        kanban.comenta(equip, spec, request.user, rol, request.POST.get("text", ""))
    except kanban.ErrorKanban as error:
        return _error(str(error))
    return _resposta_tauler(request, equip, rol)


# ---- Insígnies ------------------------------------------------------------------


@login_required
def insignies_projecte(request, projecte_id):
    projecte = get_object_or_404(Projecte, pk=projecte_id)
    if not _pot_veure_insignies(request.user, projecte):
        raise Http404("Les insígnies d'aquest projecte no són visibles.")

    pot_gestionar = _pot_gestionar(request.user, projecte)
    total_specs = projecte.specs.count()
    moduls_projecte = len(projecte.mps())
    hores_projecte = sum(projecte.specs.values_list("hores_estimades", flat=True))
    meus = set(
        projecte.equips.filter(membres=request.user).values_list("pk", flat=True)
    )

    files = []
    for equip in projecte.equips.order_by("nom", "id"):
        kanban.neteja_exmembres(equip)
        fila = kanban.progres(equip, total_specs)
        fila.update(
            equip=equip,
            meu=equip.pk in meus,
            insignies=insignies.de_l_equip(equip, moduls_projecte, hores_projecte),
        )
        fila["aconseguides"] = sum(1 for i in fila["insignies"] if i["aconseguida"])
        fila["possibles"] = sum(1 for i in fila["insignies"] if not i["no_disponible"])
        files.append(fila)

    mitjana = round(sum(f["percent"] for f in files) / len(files)) if files else 0
    return render(
        request,
        "scrum/insignies.html",
        {
            "projecte": projecte,
            "files": files,
            "mitjana": mitjana,
            "aconseguides": sum(f["aconseguides"] for f in files),
            "possibles": sum(f["possibles"] for f in files),
            "pot_gestionar": pot_gestionar,
        },
    )


# ---- Seguiment del professorat ---------------------------------------------------


@login_required
def matriu_projecte(request, projecte_id):
    """Estat de cada tasca a cada equip, en una sola taula."""
    projecte = get_object_or_404(Projecte, pk=projecte_id)
    if not _pot_gestionar(request.user, projecte):
        raise Http404
    specs = list(projecte.specs.order_by("ordre", "id"))
    files = []
    for equip in projecte.equips.order_by("nom", "id").prefetch_related("membres"):
        estats = dict(
            equip.tasques.filter(spec__projecte=projecte).values_list("spec_id", "estat")
        )
        files.append(
            {
                "equip": equip,
                "progres": kanban.progres(equip, len(specs)),
                "celles": [
                    {
                        "spec": spec,
                        "estat": estats.get(spec.id, kanban.PENDENT),
                        "nom_estat": kanban.NOMS_ESTAT[estats.get(spec.id, kanban.PENDENT)],
                    }
                    for spec in specs
                ],
            }
        )
    return render(
        request,
        "scrum/matriu.html",
        {
            "projecte": projecte,
            "specs": specs,
            "files": files,
            "llegenda": [(estat, kanban.NOMS_ESTAT[estat]) for estat in kanban.ESTATS],
        },
    )


@login_required
def tasques_bloquejades(request):
    """Tots els bloquejos oberts dels projectes que gestiona qui mira."""
    projectes = (
        Projecte.objects.all()
        if request.user.is_superuser
        else Projecte.objects.filter(admins=request.user)
    )
    if not request.user.is_superuser and not projectes.exists():
        raise Http404
    bloquejos = (
        TascaBloqueig.objects.filter(
            tancat_el__isnull=True,
            tasca__estat=kanban.BLOQUEJAT,
            tasca__equip__projecte__in=projectes,
        )
        .select_related(
            "tasca__spec", "tasca__equip__projecte", "tasca__responsable", "obert_per"
        )
        .order_by("obert_el")
    )
    return render(
        request,
        "scrum/bloquejades.html",
        {"bloquejos": bloquejos, "ara": timezone.now()},
    )
