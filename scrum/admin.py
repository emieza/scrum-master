from urllib.parse import urlencode

from adminsortable2.admin import SortableAdminBase, SortableStackedInline
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelectMultiple
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Q
from django.utils.safestring import mark_safe

from .models import (
    Categoria,
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
    UnitatFormativa,
    User,
)


def _parent_id(request, segment):
    """Retorna l'id del pare a partir de la URL de l'admin."""
    parts = request.path.strip("/").split("/")
    try:
        index = parts.index(segment)
        return int(parts[index + 1])
    except (ValueError, IndexError):
        return None


class SprintInline(admin.TabularInline):
    model = Sprint
    extra = 1
    ordering = ("inici",)
    fields = ("nom", "inici", "final", "total_hores")
    readonly_fields = ("total_hores",)

    def total_hores(self, obj):
        return obj.hores if obj and obj.pk else 0

    total_hores.short_description = "Hores"


class ProjecteAutocompleteSelectMultiple(AutocompleteSelectMultiple):
    def __init__(self, field, admin_site, projecte_id, attrs=None, choices=()):
        self.projecte_id = projecte_id
        super().__init__(field, admin_site, attrs=attrs, choices=choices)

    def get_url(self):
        url = super().get_url()
        if self.projecte_id:
            url = "{}?{}".format(url, urlencode({"projecte_id": self.projecte_id}))
        return url


class SpecInline(SortableStackedInline):
    model = Spec
    extra = 1
    fields = ("nom", "ordre", "mp", "hores_estimades", "sprints")
    autocomplete_fields = ("mp", "sprints")
    ordering = ("ordre",)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        projecte_id = _parent_id(request, "projecte")
        projecte = Projecte.objects.filter(pk=projecte_id).first() if projecte_id else None
        if projecte:
            if db_field.name == "mp":
                kwargs["queryset"] = ModulProfessional.objects.filter(
                    Q(cicle=projecte.cicle) | Q(cicle__isnull=True)
                ).order_by("numero", "nom")
            elif db_field.name == "sprints":
                kwargs["queryset"] = Sprint.objects.filter(
                    projecte=projecte
                ).order_by("inici")

        formfield = super().formfield_for_manytomany(db_field, request, **kwargs)
        if (
            projecte
            and db_field.name == "mp"
            and isinstance(formfield.widget, AutocompleteSelectMultiple)
        ):
            formfield.widget = ProjecteAutocompleteSelectMultiple(
                db_field,
                self.admin_site,
                projecte.id,
                attrs=formfield.widget.attrs,
                choices=formfield.choices,
            )
        return formfield


class ProjecteAdmin(SortableAdminBase, admin.ModelAdmin):
    model = Projecte
    list_display = (
        "nom",
        "centre",
        "cicle",
        "inici",
        "final",
        "total_hores",
        "resum_mps",
    )
    list_filter = ("centre", "cicle", "inici")
    search_fields = ("nom", "centre__nom", "cicle__nom")
    filter_horizontal = ("admins",)
    inlines = [SprintInline, SpecInline]
    save_on_top = True
    date_hierarchy = "inici"
    list_select_related = ("centre", "cicle")

    def total_hores(self, obj):
        return "{:.0f}".format(sum(spec.hores_estimades or 0 for spec in obj.specs.all()))

    total_hores.short_description = "Hores"

    def resum_mps(self, obj):
        res = {}
        total = 0
        for spec in obj.specs.all():
            for mp in spec.mp.all():
                mpshort = mp.nom[:4]
                res[mpshort] = res.get(mpshort, 0) + (spec.hores_estimades or 0)
                total += spec.hores_estimades or 0
        html = ""
        for mp in res:
            percent = 100 * res[mp] / total if total else 0
            html += "{}: {:.0f} ({:.0f}%)<br>\n".format(mp, res[mp], percent)
        return mark_safe(html)

    resum_mps.short_description = "Resum per MP"


class SprintAdmin(admin.ModelAdmin):
    model = Sprint
    list_display = ("nom", "projecte", "inici", "final", "total_hores")
    list_filter = ("projecte", "inici")
    search_fields = ("nom", "projecte__nom")
    ordering = ("-inici",)
    readonly_fields = ("total_hores", "show_specs")
    fields = ("nom", "projecte", "inici", "final", "notes", "total_hores", "show_specs")

    def total_hores(self, obj):
        return obj.hores if obj and obj.pk else 0

    total_hores.short_description = "Hores"

    def show_specs(self, obj):
        if not obj or not obj.pk:
            return "-"
        html = "<ol>\n"
        for spec in obj.specs.all():
            html += "<li>{}<dl>".format(spec.nom)
            html += "<dd>Hores estimades: {}</dd>".format(spec.hores_estimades)
            html += "<dd>"
            html += " ".join(mp.nom[:4] for mp in spec.mp.all())
            html += "</dd>\n"
            html += "<dd>{}</dd>\n".format(spec.descripcio)
            html += "</dl>\n"
        html += "</ol>\n"
        return mark_safe(html)

    show_specs.short_description = "Specs"


class SpecAdmin(admin.ModelAdmin):
    model = Spec
    list_display = (
        "ordre",
        "nom",
        "projecte",
        "mostra_sprints",
        "hores_estimades",
        "moduls",
    )
    list_editable = ("hores_estimades",)
    list_filter = ("projecte", "mp", "sprints")
    search_fields = ("nom", "projecte__nom", "mp__nom", "sprints__nom")
    filter_horizontal = ("mp",)
    ordering = ("projecte", "ordre")
    list_select_related = ("projecte",)

    def mostra_sprints(self, obj):
        return mark_safe("<br>".join(sprint.nom for sprint in obj.sprints.all()))

    mostra_sprints.short_description = "Sprints"

    def moduls(self, obj):
        return mark_safe("<br>".join(mp.nom for mp in obj.mp.all()))

    moduls.short_description = "MP"

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        spec_id = _parent_id(request, "spec")
        spec = self.get_object(request, spec_id) if spec_id else None
        if spec and db_field.name == "mp":
            kwargs["queryset"] = ModulProfessional.objects.filter(
                Q(cicle=spec.projecte.cicle) | Q(cicle__isnull=True)
            ).order_by("numero", "nom")
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class EquipAdmin(admin.ModelAdmin):
    model = Equip
    list_display = ("nom", "projecte", "show_membres")
    list_filter = ("projecte",)
    search_fields = ("nom", "projecte__nom", "membres__email")
    filter_horizontal = ("membres",)

    def show_membres(self, obj):
        html = ""
        for membre in obj.membres.all():
            html += '{} {} (<a href="/admin/scrum/user/{}/change/">{}</a>)<br>\n'.format(
                membre.first_name,
                membre.last_name,
                membre.id,
                membre.username,
            )
        return mark_safe(html)

    show_membres.short_description = "Membres"


class QualificacioInline(admin.TabularInline):
    model = Qualificacio
    extra = 0
    fields = ("sprint", "nota", "specs_completades", "hores_completades")
    readonly_fields = ("sprint", "specs_completades", "hores_completades")
    show_change_link = True


class DoneSpecInline(admin.TabularInline):
    model = DoneSpec
    extra = 0
    can_delete = False
    ordering = ("spec__ordre", "spec__id")
    fields = ("spec", "is_done", "hores_estimades", "descripcio", "mps")
    readonly_fields = ("spec", "is_done", "hores_estimades", "descripcio", "mps")

    def is_done(self, obj):
        return obj.done

    is_done.boolean = True
    is_done.short_description = "Feta"

    def hores_estimades(self, obj):
        return obj.spec.hores_estimades

    def descripcio(self, obj):
        return mark_safe(obj.spec.descripcio)

    def mps(self, obj):
        return mark_safe("<br>".join(mp.nom for mp in obj.spec.mp.all()))


class QualificacioAdmin(admin.ModelAdmin):
    model = Qualificacio
    list_display = (
        "__str__",
        "projecte",
        "sprint",
        "equip",
        "membres",
        "nota",
        "specs_completades",
        "hores_completades",
        "specs_completades_mps",
        "specs_completades_mps_ponderat",
    )
    list_filter = ("sprint__projecte", "sprint")
    search_fields = ("sprint__projecte__nom", "sprint__nom", "equip__nom")
    readonly_fields = (
        "specs_completades",
        "hores_completades",
        "specs_completades_mps",
        "specs_completades_mps_ponderat",
    )
    inlines = [DoneSpecInline]

    def projecte(self, obj):
        return obj.sprint.projecte.nom

    def specs_completades(self, obj):
        return obj.specs_completades()

    def hores_completades(self, obj):
        return obj.hores_completades()

    def specs_completades_mps(self, obj):
        return obj.specs_completades_mps()

    def specs_completades_mps_ponderat(self, obj):
        return obj.specs_completades_mps_ponderat()


class SpecFeedbackAdmin(admin.ModelAdmin):
    model = SpecFeedback
    list_display = ("spec", "projecte", "usuari", "equip", "hores", "data")
    list_filter = ("spec__projecte", "equip", "data")
    search_fields = ("spec__nom", "spec__projecte__nom", "usuari__email")
    readonly_fields = ("data",)

    def projecte(self, obj):
        return obj.spec.projecte


class CentreAdmin(admin.ModelAdmin):
    model = Centre
    list_display = ("nom", "poblacio", "cp", "email", "web")
    list_filter = ("poblacio",)
    search_fields = ("nom", "poblacio", "codi")
    filter_horizontal = ("admins", "cicles")


class ModulProfessionalInline(admin.TabularInline):
    model = ModulProfessional
    extra = 1
    fields = ("numero", "nom", "descripcio")
    ordering = ("numero", "nom")


class CicleAdmin(admin.ModelAdmin):
    model = Cicle
    list_display = ("codi", "nom", "grau", "familia")
    list_filter = ("grau", "familia")
    search_fields = ("codi", "nom")
    inlines = [ModulProfessionalInline]
    save_on_top = True


class CategoriaAdmin(admin.ModelAdmin):
    model = Categoria
    list_display = ("nom", "pare")
    search_fields = ("nom",)


class ModulProfessionalAdmin(admin.ModelAdmin):
    model = ModulProfessional
    list_display = ("numero", "nom", "cicle")
    list_filter = ("cicle",)
    search_fields = ("nom", "cicle__nom")
    ordering = ("cicle", "numero")


class UnitatFormativaAdmin(admin.ModelAdmin):
    model = UnitatFormativa
    list_display = ("numero", "nom", "mp")
    list_filter = ("mp__cicle",)
    search_fields = ("nom", "mp__nom")


class UserAdmin(BaseUserAdmin):
    model = User
    list_display = (
        "email",
        "username",
        "first_name",
        "last_name",
        "centre",
        "is_staff",
        "is_active",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "centre", "groups")
    search_fields = ("email", "username", "first_name", "last_name")
    ordering = ("email",)
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Perfil Scrum",
            {"fields": ("centre", "imatge", "descripcio")},
        ),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "Perfil Scrum",
            {"fields": ("email", "first_name", "last_name", "centre")},
        ),
    )


admin.site.site_header = "Scrum Master · Administració"
admin.site.site_title = "Scrum Master"
admin.site.index_title = "Gestió de projectes Scrum / ABP"

admin.site.register(Categoria, CategoriaAdmin)
admin.site.register(Cicle, CicleAdmin)
admin.site.register(Centre, CentreAdmin)
admin.site.register(ModulProfessional, ModulProfessionalAdmin)
admin.site.register(UnitatFormativa, UnitatFormativaAdmin)
admin.site.register(Projecte, ProjecteAdmin)
admin.site.register(Equip, EquipAdmin)
admin.site.register(Sprint, SprintAdmin)
admin.site.register(Spec, SpecAdmin)
admin.site.register(Qualificacio, QualificacioAdmin)
admin.site.register(SpecFeedback, SpecFeedbackAdmin)
admin.site.register(User, UserAdmin)
