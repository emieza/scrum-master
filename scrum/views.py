import datetime
import io
import re

from django.contrib import messages
from django.contrib.admin.views.autocomplete import AutocompleteJsonView
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST
from odf.opendocument import OpenDocumentSpreadsheet
from odf.style import Style, TableCellProperties, TextProperties
from odf.table import Table, TableCell, TableRow
from odf.text import P

from .forms import ProjecteDescripcioForm, SpecDescripcioForm
from .models import (
    Centre,
    Cicle,
    DoneSpec,
    Equip,
    ModulProfessional,
    Projecte,
    Qualificacio,
    Spec,
    SpecFeedback,
    Sprint,
    User,
)


class ProjecteAutocompleteJsonView(AutocompleteJsonView):
    """Limita els MPs i els sprints de les specs al projecte triat."""

    def get_queryset(self):
        qs = super().get_queryset()
        if self.model_admin.model not in (ModulProfessional, Sprint):
            return qs

        projecte_id = self.request.GET.get("projecte_id")
        if not projecte_id:
            return qs

        projecte = Projecte.objects.filter(pk=projecte_id).first()
        if projecte is None:
            return qs.none()

        if self.model_admin.model is Sprint:
            return qs.filter(projecte=projecte)
        return qs.filter(Q(cicle=projecte.cicle) | Q(cicle__isnull=True))


def index(request):
    projectes = (
        Projecte.objects.select_related("centre", "cicle")
        .prefetch_related("sprints")
        .order_by("-inici")
    )
    return render(request, "scrum/projecte_list.html", {"projectes": projectes})


def projecte(request, id):
    projecte = get_object_or_404(
        Projecte.objects.select_related("centre", "cicle"), pk=id
    )

    toggled_comment = None
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect("login")

        spec = get_object_or_404(
            Spec, pk=request.POST.get("spec_id"), projecte=projecte
        )
        sprint_id = request.POST.get("sprint_id")

        equip = request.user.equips.filter(projecte=projecte).first()
        if equip is None and not (
            request.user.es_profe or request.user.is_superuser
        ):
            messages.error(
                request, "No formes part de cap equip d'aquest projecte."
            )
            return redirect("projecte", id=projecte.id)

        hores = request.POST.get("hores") or None
        try:
            hores = float(hores) if hores is not None else None
        except ValueError:
            hores = None

        SpecFeedback.objects.create(
            spec=spec,
            usuari=request.user,
            equip=equip,
            hores=hores,
            desc=request.POST.get("desc", "").strip(),
        )
        toggled_comment = {"sprint_id": sprint_id, "spec_id": spec.id}
        messages.success(request, "Comentari afegit correctament.")

    activa_comentaris = False
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.es_profe:
            activa_comentaris = True
        elif request.user.equips.filter(projecte=projecte).exists():
            activa_comentaris = True

    return render(
        request,
        "scrum/projecte.html",
        {
            "projecte": projecte,
            "mps": projecte.mps(),
            "specs_backlog": projecte.specs.filter(
                sprints__isnull=True
            ).order_by("ordre", "id"),
            "toggled_comment": toggled_comment,
            "activa_comentaris": activa_comentaris,
        },
    )


NOU_CENTRE_CAMPS = (
    "nom",
    "direccio",
    "poblacio",
    "cp",
    "telefon",
    "codi",
    "email",
    "web",
    "descripcio",
    "imatge",
)


def _nou_centre_buit():
    return {camp: "" for camp in NOU_CENTRE_CAMPS} | {"cicles": []}


@login_required
def perfil(request):
    centre_actual = request.user.centre
    dades = {
        "first_name": request.user.first_name,
        "last_name": request.user.last_name,
        "centre": centre_actual.pk if centre_actual else "",
        "centre_nom": str(centre_actual) if centre_actual else "",
        "nou_centre": _nou_centre_buit(),
        "crea_centre": False,
    }
    errors = []

    if request.method == "POST":
        dades["first_name"] = request.POST.get("first_name", "").strip()
        dades["last_name"] = request.POST.get("last_name", "").strip()
        dades["nou_centre"] = {
            camp: request.POST.get(f"nou_centre_{camp}", "").strip()
            for camp in NOU_CENTRE_CAMPS
        }
        dades["nou_centre"]["cicles"] = [
            int(valor)
            for valor in request.POST.getlist("nou_centre_cicles")
            if valor.isdigit()
        ]
        centre_id = request.POST.get("centre", "").strip()
        dades["centre"] = centre_id

        crea_centre = (
            bool(request.POST.get("crea_centre"))
            or any(dades["nou_centre"][camp] for camp in NOU_CENTRE_CAMPS)
            or bool(dades["nou_centre"]["cicles"])
        )
        dades["crea_centre"] = crea_centre
        centre = None

        if crea_centre:
            nou = dades["nou_centre"]
            if not nou["nom"]:
                errors.append("El nom del centre és obligatori.")
            if not nou["poblacio"]:
                errors.append("La població del centre és obligatòria.")
            if not nou["cp"]:
                errors.append("El codi postal del centre és obligatori.")
            elif not (len(nou["cp"]) == 5 and nou["cp"].isdigit()):
                errors.append("El codi postal ha de tenir 5 dígits.")
            if nou["telefon"] and not re.fullmatch(r"[0-9 +().-]{5,20}", nou["telefon"]):
                errors.append("El telèfon del centre no és vàlid.")
            if nou["codi"] and not nou["codi"].isdigit():
                errors.append("El codi del centre ha de ser un número.")
            if not nou["email"]:
                errors.append("El correu del centre és obligatori.")
            elif "@" not in nou["email"]:
                errors.append("El correu del centre no és vàlid.")
            elif Centre.objects.filter(
                nom__iexact=nou["nom"], poblacio__iexact=nou["poblacio"]
            ).exists():
                errors.append("Ja existeix un centre amb aquest nom i població.")
            validador_url = URLValidator()
            for camp, etiqueta in (("web", "web"), ("imatge", "imatge")):
                if nou[camp]:
                    try:
                        validador_url(nou[camp])
                    except ValidationError:
                        errors.append(f"La {etiqueta} del centre no és una URL vàlida.")
            if dades["nou_centre"]["cicles"] and Cicle.objects.filter(
                pk__in=dades["nou_centre"]["cicles"]
            ).count() != len(dades["nou_centre"]["cicles"]):
                errors.append("Hi ha cicles del centre no vàlids.")
        elif centre_id:
            if centre_id.isdigit():
                centre = Centre.objects.filter(pk=centre_id).first()
            if centre is None:
                errors.append("Tria un centre educatiu vàlid.")
            else:
                dades["centre_nom"] = str(centre)

        if not dades["first_name"]:
            errors.append("El nom és obligatori.")
        if not dades["last_name"]:
            errors.append("El cognom és obligatori.")

        if not errors:
            if crea_centre:
                nou = dades["nou_centre"]
                centre = Centre.objects.create(
                    nom=nou["nom"],
                    direccio=nou["direccio"],
                    poblacio=nou["poblacio"],
                    cp=nou["cp"],
                    telefon=nou["telefon"],
                    codi=int(nou["codi"] or 0),
                    email=nou["email"],
                    web=nou["web"],
                    descripcio=nou["descripcio"],
                    imatge=nou["imatge"],
                )
                centre.cicles.set(Cicle.objects.filter(pk__in=nou["cicles"]))
            usuari = request.user
            usuari.first_name = dades["first_name"]
            usuari.last_name = dades["last_name"]
            usuari.centre = centre
            usuari.save(update_fields=["first_name", "last_name", "centre"])
            messages.success(request, "Perfil actualitzat correctament.")
            return redirect("perfil")

    return render(
        request,
        "scrum/perfil.html",
        {
            "dades": dades,
            "errors": errors,
            "cicles": Cicle.objects.all(),
        },
    )


@login_required
def cerca_centres(request):
    terme = request.GET.get("q", "").strip()
    resultats = []

    if terme:
        centres = Centre.objects.filter(
            Q(nom__icontains=terme) | Q(poblacio__icontains=terme)
        ).order_by("nom")[:10]
        resultats = [
            {
                "id": centre.pk,
                "nom": centre.nom,
                "poblacio": centre.poblacio,
                "label": "{} ({})".format(centre.nom, centre.poblacio),
            }
            for centre in centres
        ]

    return JsonResponse({"results": resultats})


@login_required
def cerca_cicles(request):
    terme = request.GET.get("q", "").strip()
    resultats = []

    if terme:
        cicles = Cicle.objects.filter(
            Q(nom__icontains=terme)
            | Q(codi__icontains=terme)
            | Q(grau__icontains=terme)
        ).order_by("nom")[:10]
        resultats = [
            {
                "id": cicle.pk,
                "label": "{} ({})".format(cicle, cicle.codi),
            }
            for cicle in cicles
        ]

    return JsonResponse({"results": resultats})


@login_required
def cerca_moduls(request):
    projecte = get_object_or_404(
        Projecte,
        pk=request.GET.get("projecte_id"),
        admins=request.user,
    )
    terme = request.GET.get("q", "").strip()
    resultats = []

    if terme:
        moduls = _moduls_per_projecte(projecte).filter(nom__icontains=terme)[:10]
        resultats = [
            {
                "id": modul.pk,
                "label": str(modul),
            }
            for modul in moduls
        ]

    return JsonResponse({"results": resultats})


@login_required
def cerca_sprints(request):
    projecte = get_object_or_404(
        Projecte,
        pk=request.GET.get("projecte_id"),
        admins=request.user,
    )
    terme = request.GET.get("q", "").strip()
    resultats = []

    if terme:
        sprints = projecte.sprints.filter(nom__icontains=terme)[:10]
        resultats = [
            {
                "id": sprint.pk,
                "label": sprint.nom,
            }
            for sprint in sprints
        ]

    return JsonResponse({"results": resultats})


def _projectes_disponibles(user):
    if user.is_superuser:
        return Projecte.objects.all()
    return Projecte.objects.filter(admins=user).distinct()


def _projectes_per_crear_equip(user):
    """Projectes on l'usuari pot crear equips segons el seu centre."""
    if user.is_superuser:
        return Projecte.objects.all()
    if user.centre_id:
        return Projecte.objects.filter(centre=user.centre)
    return Projecte.objects.filter(centre__isnull=True)


@login_required
def els_meus_projectes(request):
    projectes = (
        Projecte.objects.filter(admins=request.user)
        .select_related("centre", "cicle")
        .prefetch_related("sprints")
        .order_by("-inici")
    )
    return render(request, "scrum/meus_projectes.html", {"projectes": projectes})


def _peticio_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _projecte_form(request, projecte=None):
    es_edicio = projecte is not None
    centres = Centre.objects.order_by("nom")
    cicles = Cicle.objects.order_by("nom")
    avui = datetime.date.today()

    if projecte is None:
        dades = {
            "nom": "",
            "descripcio": "",
            "centre": str(request.user.centre_id) if request.user.centre_id else "",
            "centre_nom": str(request.user.centre) if request.user.centre_id else "",
            "cicle": "",
            "cicle_nom": "",
            "inici": avui.isoformat(),
            "final": (avui + datetime.timedelta(days=30)).isoformat(),
        }
    else:
        dades = {
            "nom": projecte.nom,
            "descripcio": projecte.descripcio,
            "centre": str(projecte.centre_id) if projecte.centre_id else "",
            "centre_nom": str(projecte.centre) if projecte.centre_id else "",
            "cicle": str(projecte.cicle_id) if projecte.cicle_id else "",
            "cicle_nom": str(projecte.cicle) if projecte.cicle_id else "",
            "inici": projecte.inici.isoformat(),
            "final": projecte.final.isoformat(),
        }
    errors = []

    if request.method == "POST":
        for camp in ("nom", "descripcio", "centre", "cicle", "inici", "final"):
            dades[camp] = request.POST.get(camp, "").strip()
        if "centre" not in request.POST and request.user.centre_id:
            dades["centre"] = str(request.user.centre_id)

        centre = None
        if dades["centre"]:
            if dades["centre"].isdigit():
                centre = centres.filter(pk=dades["centre"]).first()
            if centre is None:
                errors.append("Tria un centre vàlid.")
                dades["centre"] = ""
        dades["centre_nom"] = str(centre) if centre else ""

        cicle = None
        if dades["cicle"]:
            if dades["cicle"].isdigit():
                cicle = cicles.filter(pk=dades["cicle"]).first()
            if cicle is None:
                errors.append("Tria un cicle vàlid.")
                dades["cicle"] = ""
        dades["cicle_nom"] = str(cicle) if cicle else ""

        inici = None
        try:
            inici = datetime.date.fromisoformat(dades["inici"])
        except ValueError:
            errors.append("La data d'inici no és vàlida.")

        final = None
        try:
            final = datetime.date.fromisoformat(dades["final"])
        except ValueError:
            errors.append("La data final no és vàlida.")

        if inici and final and final < inici:
            errors.append("La data final ha de ser posterior a la data d'inici.")

        if not dades["nom"]:
            errors.append("El nom del projecte és obligatori.")

        if not errors:
            if projecte is None:
                projecte = Projecte.objects.create(
                    nom=dades["nom"],
                    descripcio=dades["descripcio"],
                    centre=centre,
                    cicle=cicle,
                    inici=inici,
                    final=final,
                )
                projecte.admins.add(request.user)
                missatge = "Projecte «{}» creat correctament.".format(projecte.nom)
            else:
                projecte.nom = dades["nom"]
                projecte.descripcio = dades["descripcio"]
                projecte.centre = centre
                projecte.cicle = cicle
                projecte.inici = inici
                projecte.final = final
                projecte.save()
                missatge = "Projecte «{}» actualitzat correctament.".format(
                    projecte.nom
                )

            if _peticio_ajax(request):
                if not es_edicio:
                    return JsonResponse(
                        {
                            "ok": True,
                            "missatge": missatge,
                            "redirect": reverse("els_meus_projectes"),
                        }
                    )
                return JsonResponse(
                    {
                        "ok": True,
                        "missatge": missatge,
                        "nom": projecte.nom,
                        "descripcio": projecte.descripcio,
                    }
                )

            messages.success(request, missatge)
            return redirect("els_meus_projectes")

        if _peticio_ajax(request):
            return JsonResponse({"ok": False, "errors": errors}, status=400)

    if projecte:
        specs = projecte.specs.order_by("ordre", "id")
        moduls = _moduls_per_projecte(projecte)
        ordre_nova_spec = max((spec.ordre for spec in specs), default=0) + 1
    else:
        specs = []
        moduls = []
        ordre_nova_spec = 1

    return render(
        request,
        "scrum/projecte_form.html",
        {
            "projecte": projecte,
            "dades": dades,
            "errors": errors,
            "sprints": projecte.sprints.all() if projecte else [],
            "sprint_inici": avui.isoformat(),
            "sprint_final": (avui + datetime.timedelta(days=7)).isoformat(),
            "specs": specs,
            "moduls": moduls,
            "ordre_nova_spec": ordre_nova_spec,
            "descripcio_form": ProjecteDescripcioForm(
                initial={"descripcio": dades["descripcio"]},
                auto_id="projecte_%s",
            ),
            "spec_descripcio_form": SpecDescripcioForm(auto_id="spec_%s"),
            "spec_edit_descripcio_form": SpecDescripcioForm(
                auto_id="spec_edit_%s"
            ),
        },
    )


@login_required
def crea_projecte(request):
    return _projecte_form(request)


@login_required
def edita_projecte(request, id):
    projecte = get_object_or_404(Projecte, pk=id, admins=request.user)
    return _projecte_form(request, projecte)


@login_required
def elimina_projecte(request, id):
    projecte = get_object_or_404(Projecte, pk=id, admins=request.user)
    if request.method == "POST":
        nom = projecte.nom
        projecte.delete()
        messages.success(request, "Projecte «{}» eliminat correctament.".format(nom))
    return redirect("els_meus_projectes")


def _moduls_per_projecte(projecte):
    moduls = ModulProfessional.objects.all()
    if projecte.cicle_id:
        moduls = moduls.filter(Q(cicle=projecte.cicle) | Q(cicle__isnull=True))
    return moduls.order_by("numero", "nom")


def _valida_sprint(request):
    nom = request.POST.get("nom", "").strip()
    inici_str = request.POST.get("inici", "").strip()
    final_str = request.POST.get("final", "").strip()
    errors = []

    if not nom:
        errors.append("El nom del sprint és obligatori.")

    inici = None
    try:
        inici = datetime.date.fromisoformat(inici_str)
    except ValueError:
        errors.append("La data d'inici no és vàlida.")

    final = None
    try:
        final = datetime.date.fromisoformat(final_str)
    except ValueError:
        errors.append("La data final no és vàlida.")

    if inici and final and final < inici:
        errors.append("La data final ha de ser posterior o igual a la data d'inici.")

    return nom, inici, final, errors


def _valida_spec(request):
    nom = request.POST.get("nom", "").strip()
    descripcio = request.POST.get("descripcio", "").strip()
    errors = []

    if not nom:
        errors.append("El nom de la spec és obligatori.")

    try:
        ordre = int(request.POST.get("ordre", "0"))
        if ordre < 0:
            raise ValueError
    except ValueError:
        errors.append("L'ordre ha de ser un nombre enter positiu.")
        ordre = 0

    try:
        hores = float(request.POST.get("hores_estimades", "0") or 0)
        if hores < 0:
            raise ValueError
    except ValueError:
        errors.append("Les hores estimades han de ser un nombre positiu.")
        hores = 0

    return nom, descripcio, ordre, hores, errors


@login_required
def crea_spec(request, projecte_id):
    projecte = get_object_or_404(Projecte, pk=projecte_id, admins=request.user)
    if request.method == "POST":
        nom, descripcio, ordre, hores, errors = _valida_spec(request)

        if errors:
            if _peticio_ajax(request):
                return JsonResponse({"ok": False, "errors": errors}, status=400)
            for error in errors:
                messages.error(request, error)
        else:
            spec = Spec.objects.create(
                nom=nom,
                descripcio=descripcio,
                projecte=projecte,
                ordre=ordre,
                hores_estimades=hores,
            )
            moduls = _moduls_per_projecte(projecte)
            spec.mp.set(
                moduls.filter(pk__in=request.POST.getlist("mp"))
            )
            spec.sprints.set(
                projecte.sprints.filter(pk__in=request.POST.getlist("sprints"))
            )
            missatge = "Spec «{}» creada correctament.".format(nom)

            if _peticio_ajax(request):
                specs = projecte.specs.order_by("ordre", "id")
                html = render_to_string(
                    "scrum/_specs_llistat.html",
                    {"specs": specs},
                    request=request,
                )
                ordre_nova_spec = max(
                    (spec.ordre for spec in specs), default=0
                ) + 1
                return JsonResponse(
                    {
                        "ok": True,
                        "missatge": missatge,
                        "html": html,
                        "ordre_nova_spec": ordre_nova_spec,
                    }
                )

            messages.success(request, missatge)
    return redirect("edita_projecte", id=projecte.id)


@login_required
@require_POST
def actualitza_spec(request, id):
    spec = get_object_or_404(Spec, pk=id, projecte__admins=request.user)
    projecte = spec.projecte
    nom, descripcio, ordre, hores, errors = _valida_spec(request)

    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    spec.nom = nom
    spec.descripcio = descripcio
    spec.ordre = ordre
    spec.hores_estimades = hores
    spec.save()
    spec.mp.set(
        _moduls_per_projecte(projecte).filter(
            pk__in=request.POST.getlist("mp")
        )
    )
    spec.sprints.set(
        projecte.sprints.filter(pk__in=request.POST.getlist("sprints"))
    )

    specs = projecte.specs.order_by("ordre", "id")
    html = render_to_string(
        "scrum/_specs_llistat.html",
        {"specs": specs},
        request=request,
    )
    ordre_nova_spec = max(
        (spec.ordre for spec in specs), default=0
    ) + 1
    return JsonResponse(
        {
            "ok": True,
            "missatge": "Spec «{}» actualitzada correctament.".format(nom),
            "html": html,
            "ordre_nova_spec": ordre_nova_spec,
        }
    )


@login_required
@require_POST
def reordena_specs(request, projecte_id):
    projecte = get_object_or_404(Projecte, pk=projecte_id, admins=request.user)
    ids = request.POST.getlist("ids")

    try:
        ids = [int(spec_id) for spec_id in ids]
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "errors": ["L'ordre de les specs no és vàlid."]},
            status=400,
        )

    if len(ids) != len(set(ids)):
        return JsonResponse(
            {"ok": False, "errors": ["L'ordre de les specs no és vàlid."]},
            status=400,
        )

    ids_actuals = set(projecte.specs.values_list("id", flat=True))
    if set(ids) != ids_actuals:
        return JsonResponse(
            {
                "ok": False,
                "errors": ["Cal enviar totes les specs del projecte."],
            },
            status=400,
        )

    specs = {spec.id: spec for spec in projecte.specs.filter(pk__in=ids)}
    for index, spec_id in enumerate(ids, start=1):
        specs[spec_id].ordre = index
    if ids:
        Spec.objects.bulk_update(
            [specs[spec_id] for spec_id in ids], ["ordre"]
        )

    specs_ordenades = projecte.specs.order_by("ordre", "id")
    html = render_to_string(
        "scrum/_specs_llistat.html",
        {"specs": specs_ordenades},
        request=request,
    )
    return JsonResponse(
        {
            "ok": True,
            "missatge": "Ordre de les specs desat correctament.",
            "html": html,
            "ordre_nova_spec": len(ids) + 1,
        }
    )


@login_required
def crea_sprint(request, projecte_id):
    projecte = get_object_or_404(Projecte, pk=projecte_id, admins=request.user)
    if request.method == "POST":
        nom, inici, final, errors = _valida_sprint(request)
        if errors:
            if _peticio_ajax(request):
                return JsonResponse({"ok": False, "errors": errors}, status=400)
            for error in errors:
                messages.error(request, error)
        else:
            Sprint.objects.create(
                nom=nom,
                projecte=projecte,
                inici=inici,
                final=final,
            )
            missatge = "Sprint «{}» creat correctament.".format(nom)

            if _peticio_ajax(request):
                html = render_to_string(
                    "scrum/_sprint_llistat.html",
                    {"sprints": projecte.sprints.all()},
                    request=request,
                )
                return JsonResponse(
                    {"ok": True, "missatge": missatge, "html": html}
                )

            messages.success(request, missatge)
    return redirect("edita_projecte", id=projecte.id)


@login_required
def edita_sprint(request, id):
    sprint = get_object_or_404(Sprint, pk=id, projecte__admins=request.user)
    if request.method == "POST":
        nom, inici, final, errors = _valida_sprint(request)
        if errors:
            if _peticio_ajax(request):
                return JsonResponse({"ok": False, "errors": errors}, status=400)
            for error in errors:
                messages.error(request, error)
        else:
            sprint.nom = nom
            sprint.inici = inici
            sprint.final = final
            sprint.save()
            missatge = "Sprint «{}» actualitzat correctament.".format(nom)

            if _peticio_ajax(request):
                html = render_to_string(
                    "scrum/_sprint_llistat.html",
                    {"sprints": sprint.projecte.sprints.all()},
                    request=request,
                )
                return JsonResponse(
                    {"ok": True, "missatge": missatge, "html": html}
                )

            messages.success(request, missatge)
    return redirect("edita_projecte", id=sprint.projecte_id)


@login_required
def els_meus_equips(request):
    equips = (
        Equip.objects.filter(membres=request.user)
        .select_related("projecte", "projecte__centre")
        .prefetch_related("membres")
        .order_by("projecte__nom", "nom")
    )
    return render(request, "scrum/equips_list.html", {"equips": equips})


@login_required
def crea_equip(request):
    projectes = (
        _projectes_per_crear_equip(request.user)
        .select_related("centre")
        .order_by("nom")
    )
    dades = {"nom": "", "descripcio": "", "projecte": ""}
    errors = []

    if request.method == "POST":
        dades["nom"] = request.POST.get("nom", "").strip()
        dades["descripcio"] = request.POST.get("descripcio", "").strip()
        dades["projecte"] = request.POST.get("projecte", "").strip()
        membres_ids = request.POST.getlist("membres")

        projecte = None
        if dades["projecte"].isdigit():
            projecte = projectes.filter(pk=dades["projecte"]).first()
        if projecte is None:
            errors.append("Tria un projecte vàlid.")

        if not dades["nom"]:
            errors.append("El nom de l'equip és obligatori.")
        elif projecte and Equip.objects.filter(
            projecte=projecte, nom__iexact=dades["nom"]
        ).exists():
            errors.append("Ja existeix un equip amb aquest nom en aquest projecte.")

        if not errors:
            equip = Equip.objects.create(
                nom=dades["nom"],
                descripcio=dades["descripcio"],
                projecte=projecte,
            )
            equip.membres.set(User.objects.filter(pk__in=membres_ids))
            equip.membres.add(request.user)
            messages.success(
                request, "Equip «{}» creat correctament.".format(equip.nom)
            )
            return redirect("crea_equip")

    return render(
        request,
        "scrum/equip_form.html",
        {"projectes": projectes, "dades": dades, "errors": errors},
    )


@login_required
def cerca_usuaris(request):
    """Cerca usuaris per email i només en retorna un si la coincidència és única."""
    terme = request.GET.get("q", "").strip()
    resultats = []

    if terme:
        usuaris = list(
            User.objects.filter(is_active=True, email__icontains=terme)
            .order_by("email")[:2]
        )
        if len(usuaris) == 1:
            usuari = usuaris[0]
            resultats.append(
                {
                    "id": usuari.pk,
                    "email": usuari.email,
                    "nom": usuari.nom_complert or usuari.email,
                }
            )

    return JsonResponse({"results": resultats})


@login_required
def qualifica(request):
    projectes = _projectes_disponibles(request.user).order_by("-inici")
    projecte = None

    projecte_id = request.GET.get("projecte_id")
    if projecte_id and projecte_id.isdigit():
        projecte = get_object_or_404(Projecte, pk=projecte_id)
        if not request.user.is_superuser and not projecte.admins.filter(
            pk=request.user.pk
        ).exists():
            raise Http404
    return render(
        request,
        "scrum/qualifica.html",
        {"projectes": projectes, "projecte": projecte},
    )


@login_required
def qualifica_projecte(request, projecte_id):
    projecte = get_object_or_404(
        _projectes_disponibles(request.user), pk=projecte_id
    )
    return render(
        request,
        "scrum/qualifica.html",
        {"projectes": [], "projecte": projecte, "projecte_fixat": True},
    )


def _percentatge(total, done):
    return 100 * done / total if total else 0


def _nom_worksheet(mp, usats):
    """Retorna un nom de taula vàlid i únic per a l'ODS."""
    nom = re.sub(r"[\[\]:*?/\\]", "-", mp.nom).strip("'") or "MP {}".format(
        mp.numero
    )
    nom = nom[:31]
    base = nom
    numero = 2
    while nom.lower() in usats:
        sufix = " ({})".format(numero)
        nom = base[: 31 - len(sufix)] + sufix
        numero += 1
    usats.add(nom.lower())
    return nom


def _dades_qualificacions(projecte):
    """Prepara les dades de cada mòdul per a l'exportació a full de càlcul."""
    sprints = list(projecte.sprints.all())
    mps = list(projecte.mps())
    dades = {mp.id: [] for mp in mps}

    for equip in projecte.equips.prefetch_related("membres", "qualificacions"):
        qualificacions = {
            quali.sprint_id: quali for quali in equip.qualificacions.all()
        }
        dades_per_sprint = {
            sprint_id: {
                dada["obj"].id: dada for dada in quali.percentatges_mps()
            }
            for sprint_id, quali in qualificacions.items()
        }
        for alumne in equip.membres.all():
            for mp in mps:
                parcials = {}
                total = 0
                done = 0
                for sprint in sprints:
                    dada = dades_per_sprint.get(sprint.id, {}).get(mp.id)
                    if dada:
                        parcials[sprint.id] = {
                            "total": dada["total"],
                            "done": dada["done"],
                            "percentatge": dada["percentatge_text"],
                        }
                        total += dada["total"]
                        done += dada["done"]
                    else:
                        parcials[sprint.id] = None
                dades[mp.id].append(
                    {
                        "alumne": alumne,
                        "equip": equip,
                        "parcials": parcials,
                        "total": total,
                        "done": done,
                    }
                )
    return sprints, mps, dades


def _text_ods(text, style=None):
    cell = TableCell(valuetype="string")
    if style is not None:
        cell.setAttribute("stylename", style)
    cell.addElement(P(text=str(text)))
    return cell


def _number_ods(value):
    return TableCell(valuetype="float", value=float(value))


@login_required
def descarrega_qualificacions(request, projecte_id):
    projecte = get_object_or_404(Projecte, pk=projecte_id)
    if not request.user.is_superuser and not projecte.admins.filter(
        pk=request.user.pk
    ).exists():
        raise Http404

    sprints, mps, dades = _dades_qualificacions(projecte)

    document = OpenDocumentSpreadsheet()
    header_style = Style(name="HeaderCell", family="table-cell")
    header_style.addElement(
        TableCellProperties(
            backgroundcolor="#455a64",
            border="0.02cm solid #000000",
            padding="0.1cm",
        )
    )
    header_style.addElement(
        TextProperties(color="#ffffff", fontweight="bold")
    )
    document.automaticstyles.addElement(header_style)
    usats = set()

    for mp in mps:
        table = Table(name=_nom_worksheet(mp, usats))
        headers = ["Cognoms", "Nom", "Email", "Equip"]
        for sprint in sprints:
            headers += [
                "{} - Hores planificades".format(sprint.nom),
                "{} - Hores completades".format(sprint.nom),
                "{} - Percentatge".format(sprint.nom),
            ]
        headers += [
            "Hores totals",
            "Hores completades",
            "Percentatge total",
        ]

        row = TableRow()
        for titol in headers:
            row.addElement(_text_ods(titol, header_style))
        table.addElement(row)

        for files in dades[mp.id]:
            alumne = files["alumne"]
            equip = files["equip"]
            row = TableRow()
            row.addElement(_text_ods(alumne.last_name or ""))
            row.addElement(_text_ods(alumne.first_name or ""))
            row.addElement(_text_ods(alumne.email or ""))
            row.addElement(_text_ods(equip.nom))
            for sprint in sprints:
                parcial = files["parcials"].get(sprint.id)
                if parcial is None:
                    row.addElement(TableCell())
                    row.addElement(TableCell())
                    row.addElement(TableCell())
                else:
                    row.addElement(_number_ods(parcial["total"]))
                    row.addElement(_number_ods(parcial["done"]))
                    row.addElement(
                        _text_ods("{}%".format(parcial["percentatge"]))
                    )
            row.addElement(_number_ods(files["total"]))
            row.addElement(_number_ods(files["done"]))
            row.addElement(
                _text_ods(
                    "{:.1f}%".format(
                        _percentatge(files["total"], files["done"])
                    )
                )
            )
            table.addElement(row)

        document.spreadsheet.addElement(table)

    output = io.BytesIO()
    document.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.oasis.opendocument.spreadsheet",
    )
    response["Content-Disposition"] = (
        'attachment; filename="qualificacions_{}.ods"'.format(projecte.id)
    )
    return response


def _spec_data(spec):
    return {
        "id": spec.id,
        "ordre": spec.ordre,
        "nom": spec.nom,
        "descripcio": spec.descripcio,
        "hores_estimades": spec.hores_estimades,
        "mp": [{"id": mp.id, "nom": mp.nom} for mp in spec.mp.all()],
    }


def _done_spec_data(done_spec):
    return {
        "id": done_spec.id,
        "done": done_spec.done,
        "ordre": done_spec.ordre,
        "spec": _spec_data(done_spec.spec),
    }


def _qualificacio_data(quali):
    return {
        "id": quali.id,
        "nota": quali.nota,
        "comentaris": quali.comentaris,
        "equip": {
            "id": quali.equip.id,
            "nom": quali.equip.nom,
            "membres": [
                {
                    "first_name": membre.first_name,
                    "last_name": membre.last_name,
                    "email": membre.email,
                }
                for membre in quali.equip.membres.all()
            ],
        },
        "done_specs": [
            _done_spec_data(done_spec) for done_spec in quali.done_specs.all()
        ],
    }


def _pot_gestionar(user, projecte):
    return user.is_superuser or projecte.admins.filter(pk=user.pk).exists()


@login_required
@require_POST
def crea_qualificacio(request, sprint_id, equip_id):
    sprint = get_object_or_404(Sprint, pk=sprint_id)
    projecte = sprint.projecte
    if not _pot_gestionar(request.user, projecte):
        return JsonResponse(
            {"status": "ERROR", "message": "Falten permisos."}, status=403
        )

    equip = get_object_or_404(Equip, pk=equip_id, projecte=projecte)
    quali, created = Qualificacio.objects.get_or_create(
        equip=equip, sprint=sprint
    )
    if created:
        for spec in sprint.specs.all():
            DoneSpec.objects.get_or_create(qualificacio=quali, spec=spec)
    return JsonResponse({"status": "OK", "qualificacio_id": quali.id})


@login_required
@require_POST
def elimina_qualificacio(request, qualificacio_id):
    quali = get_object_or_404(Qualificacio, pk=qualificacio_id)
    if not _pot_gestionar(request.user, quali.sprint.projecte):
        return JsonResponse(
            {"status": "ERROR", "message": "Falten permisos."}, status=403
        )
    quali.delete()
    return JsonResponse(
        {"status": "OK", "message": "Qualificació eliminada."}
    )


@login_required
def get_done_specs(request, qualificacio_id):
    quali = get_object_or_404(Qualificacio, pk=qualificacio_id)
    if not _pot_gestionar(request.user, quali.sprint.projecte):
        return JsonResponse(
            {"status": "ERROR", "message": "Falten permisos."}, status=403
        )
    return JsonResponse(
        {
            "status": "OK",
            "done_specs": [
                _done_spec_data(done_spec)
                for done_spec in quali.done_specs.all()
            ],
        }
    )


@login_required
def get_qualificacio(request, qualificacio_id):
    quali = get_object_or_404(Qualificacio, pk=qualificacio_id)
    if not _pot_gestionar(request.user, quali.sprint.projecte):
        return JsonResponse(
            {"status": "ERROR", "message": "Falten permisos."}, status=403
        )
    return JsonResponse({"status": "OK", "qualificacio": _qualificacio_data(quali)})


@login_required
@require_POST
def toggle_done_spec(request, done_spec_id):
    done_spec = get_object_or_404(DoneSpec, pk=done_spec_id)
    if not _pot_gestionar(request.user, done_spec.spec.projecte):
        return JsonResponse(
            {"status": "ERROR", "message": "Falten permisos."}, status=403
        )
    done_spec.done = not done_spec.done
    done_spec.save(update_fields=["done"])
    return JsonResponse({"status": "OK", "done_spec": _done_spec_data(done_spec)})


@login_required
@require_POST
def set_comment_to_qualificacio(request, qualificacio_id):
    quali = get_object_or_404(Qualificacio, pk=qualificacio_id)
    if not _pot_gestionar(request.user, quali.sprint.projecte):
        return JsonResponse(
            {"status": "ERROR", "message": "Falten permisos."}, status=403
        )
    quali.comentaris = request.POST.get("comentaris", "")
    quali.save(update_fields=["comentaris"])
    return JsonResponse({"status": "OK", "message": "Comentari guardat."})
