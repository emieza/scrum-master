import io
import re

from django.contrib import messages
from django.contrib.admin.views.autocomplete import AutocompleteJsonView
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from odf.opendocument import OpenDocumentSpreadsheet
from odf.style import Style, TableCellProperties, TextProperties
from odf.table import Table, TableCell, TableRow
from odf.text import P

from .models import (
    DoneSpec,
    Equip,
    ModulProfessional,
    Projecte,
    Qualificacio,
    Spec,
    SpecFeedback,
    Sprint,
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
            "toggled_comment": toggled_comment,
            "activa_comentaris": activa_comentaris,
        },
    )


def _projectes_disponibles(user):
    if user.is_superuser:
        return Projecte.objects.all()
    return Projecte.objects.filter(admins=user).distinct()


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
