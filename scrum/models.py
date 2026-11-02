import datetime
import re
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.safestring import mark_safe
from django_ckeditor_5.fields import CKEditor5Field


class User(AbstractUser):
    """Usuari del portal: alumnat, professorat o administrador de centre."""

    email = models.EmailField("adreça de correu", unique=True)
    centre = models.ForeignKey(
        "Centre",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuaris",
        help_text="Centre on està matriculat l'alumne o on treballa el professor.",
    )
    imatge = models.URLField(blank=True, help_text="URL de la imatge de perfil.")
    descripcio = models.TextField(blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.nom_complert or self.username

    @property
    def nom_complert(self):
        return "{} {}".format(self.first_name, self.last_name).strip()

    @property
    def es_alumne(self):
        return self.groups.filter(name="alumnes").exists()

    @property
    def es_profe(self):
        return self.groups.filter(name="profes").exists()

    @property
    def es_admin_centre(self):
        return self.centres_admin.exists()


class Categoria(models.Model):
    """Família professional a la qual pertany un cicle formatiu."""

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categories"
        ordering = ["nom"]

    nom = models.CharField(max_length=255, unique=True)
    descripcio = models.TextField(blank=True)
    pare = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="fills"
    )

    def __str__(self):
        return self.nom


class Cicle(models.Model):
    """Cicle formatiu (grau mitjà o grau superior)."""

    GRAU = (
        ("CFGB", "Grau Bàsic"),
        ("CFGM", "Grau Mitjà"),
        ("CFGS", "Grau Superior"),
        ("CE", "Curs d'Especialització"),
    )

    class Meta:
        verbose_name = "cicle formatiu"
        verbose_name_plural = "cicles formatius"
        ordering = ["nom"]

    grau = models.CharField(max_length=4, choices=GRAU)
    codi = models.CharField(max_length=8, unique=True)
    nom = models.CharField(max_length=255, unique=True)
    pladestudis = models.URLField(blank=True)
    familia = models.ForeignKey(
        Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name="cicles"
    )
    descripcio = models.TextField(blank=True)

    def __str__(self):
        return self.grau + " "+ self.nom


class Centre(models.Model):
    """Centre educatiu."""

    class Meta:
        verbose_name = "centre educatiu"
        verbose_name_plural = "centres educatius"
        ordering = ["nom"]

    nom = models.CharField(max_length=255)
    direccio = models.TextField(blank=True)
    poblacio = models.CharField(max_length=255)
    cp = models.CharField("codi postal", max_length=5)
    telefon = models.CharField(max_length=20, blank=True)
    codi = models.IntegerField(default=0)
    email = models.EmailField()
    web = models.URLField(blank=True)
    descripcio = models.TextField(blank=True)
    admins = models.ManyToManyField(
        User, blank=True, related_name="centres_admin", help_text="Administradors del centre."
    )
    cicles = models.ManyToManyField(Cicle, blank=True, related_name="centres")
    imatge = models.URLField(blank=True, help_text="URL del logotip del centre.")

    def __str__(self):
        return "{} ({})".format(self.nom, self.poblacio)


class ModulProfessional(models.Model):
    """Mòdul professional d'un cicle formatiu."""

    class Meta:
        verbose_name = "mòdul professional"
        verbose_name_plural = "mòduls professionals"
        ordering = ["cicle", "numero", "nom"]

    numero = models.IntegerField(default=0)
    nom = models.CharField(max_length=255)
    descripcio = models.TextField(blank=True)
    cicle = models.ForeignKey(
        Cicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="moduls"
    )

    def __str__(self):
        num = self.numero
        return f"{num:04d}" + " " +self.nom


class Projecte(models.Model):
    """Projecte ABP gestionat amb metodologia Scrum."""

    class Meta:
        verbose_name = "projecte"
        verbose_name_plural = "projectes"
        ordering = ["-inici"]

    nom = models.CharField(max_length=255)
    descripcio = CKEditor5Field(blank=True)
    centre = models.ForeignKey(Centre, on_delete=models.CASCADE,
        related_name="projectes", blank=True, null=True)
    admins = models.ManyToManyField(
        User,
        blank=True,
        related_name="projectes_admin",
        help_text="Professionals implicats en el projecte.",
    )
    inici = models.DateField(default=datetime.date.today)
    final = models.DateField()
    cicle = models.ForeignKey(
        Cicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="projectes"
    )

    def __str__(self):
        return self.nom

    def descripcio_html(self):
        return mark_safe(self.descripcio)

    def mps(self):
        return (
            ModulProfessional.objects.filter(specs__projecte=self)
            .distinct()
            .order_by("nom")
        )


YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def _url_video(url):
    if not url:
        return None
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    return parsed


def _es_host_youtube(host):
    host = (host or "").lower()
    return (
        host == "youtu.be"
        or host == "youtube.com"
        or host.endswith(".youtube.com")
        or host == "youtube-nocookie.com"
        or host.endswith(".youtube-nocookie.com")
    )


def _extract_youtube_id(url):
    parsed = _url_video(url)
    if parsed is None or not _es_host_youtube(parsed.hostname):
        return ""

    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        candidats = [part for part in parsed.path.split("/") if part][:1]
    elif parsed.path.rstrip("/") == "/watch":
        candidats = parse_qs(parsed.query).get("v", [])
    else:
        parts = [part for part in parsed.path.split("/") if part]
        candidats = (
            [parts[1]]
            if len(parts) >= 2
            and parts[0] in ("embed", "live", "shorts")
            else []
        )

    for candidat in candidats:
        if YOUTUBE_ID_RE.fullmatch(candidat):
            return candidat
    return ""


class Equip(models.Model):
    """Equip de treball d'un projecte."""

    class Meta:
        verbose_name = "equip"
        verbose_name_plural = "equips"
        ordering = ["nom"]

    nom = models.CharField(max_length=255)
    descripcio = models.TextField(blank=True)
    projecte = models.ForeignKey(
        Projecte, on_delete=models.CASCADE, related_name="equips"
    )
    membres = models.ManyToManyField(User, blank=True, related_name="equips")
    link_video = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="enllaç del vídeo",
        help_text="Enllaç de YouTube o d'una altra plataforma de vídeo.",
    )

    def __str__(self):
        return self.nom

    def video_youtube_id(self):
        return _extract_youtube_id(self.link_video)

    def es_video_youtube(self):
        parsed = _url_video(self.link_video)
        return parsed is not None and _es_host_youtube(parsed.hostname)

    def domini_video(self):
        parsed = _url_video(self.link_video)
        host = (parsed.hostname or "") if parsed else ""
        return host[4:] if host.startswith("www.") else host


class Sprint(models.Model):
    """Iteració d'un projecte."""

    class Meta:
        verbose_name = "sprint"
        verbose_name_plural = "sprints"
        ordering = ["inici", "nom"]

    nom = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    projecte = models.ForeignKey(
        Projecte, on_delete=models.CASCADE, related_name="sprints"
    )
    inici = models.DateField()
    final = models.DateField()

    def __str__(self):
        return self.nom

    @property
    def hores(self):
        return sum(
            spec.hores_estimades or 0 for spec in self.specs.all()
        )

    def dades_mps(self):
        total_hores = 0
        total_specs = 0
        mps = {}
        for spec in self.specs.all():
            total_specs += 1
            total_hores += spec.hores_estimades or 0
            for mp in spec.mp.all():
                if mp.nom not in mps:
                    mps[mp.nom] = {"hores": 0, "specs": 0}
                mps[mp.nom]["specs"] += 1
                mps[mp.nom]["hores"] += spec.hores_estimades or 0
        for dades in mps.values():
            dades["percent_hores"] = (
                100 * dades["hores"] / total_hores if total_hores else 0
            )
            dades["percent_specs"] = (
                100 * dades["specs"] / total_specs if total_specs else 0
            )
        return mps


class Spec(models.Model):
    """Especificació o història d'usuari del producte."""

    class Meta:
        verbose_name = "spec"
        verbose_name_plural = "specs"
        ordering = ["ordre", "id"]

    nom = models.CharField(max_length=600)
    descripcio = CKEditor5Field(blank=True)
    pare = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="fills",
    )
    projecte = models.ForeignKey(
        Projecte, on_delete=models.CASCADE, related_name="specs"
    )
    ordre = models.IntegerField(default=0)
    mp = models.ManyToManyField(
        ModulProfessional,
        related_name="specs",
        blank=True,
        verbose_name="mòduls professionals",
    )
    hores_estimades = models.FloatField(default=0.0)
    sprints = models.ManyToManyField(Sprint, related_name="specs", blank=True)

    def __str__(self):
        return "{}. {}".format(self.ordre, self.nom)

    def show_sprints(self):
        return " , ".join(sprint.nom for sprint in self.sprints.all())


class Qualificacio(models.Model):
    """Avaluació d'un equip en un sprint."""

    class Meta:
        verbose_name = "qualificació"
        verbose_name_plural = "qualificacions"
        ordering = ["sprint__inici", "equip__nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["equip", "sprint"], name="unique_qualificacio_equip_sprint"
            )
        ]

    equip = models.ForeignKey(
        Equip, on_delete=models.CASCADE, related_name="qualificacions"
    )
    sprint = models.ForeignKey(
        Sprint, on_delete=models.CASCADE, related_name="qualificacions"
    )
    nota = models.FloatField(null=True, blank=True)
    comentaris = models.TextField(blank=True)

    def __str__(self):
        return "{} ({})".format(self.equip, self.sprint)

    def projecte(self):
        return self.sprint.projecte.nom

    def membres(self):
        ret = ""
        for membre in self.equip.membres.all():
            ret += "{} {}<br>\n".format(membre.first_name, membre.last_name)
        return mark_safe(ret)

    def specs_completades(self):
        total = 0
        completades = 0.0
        for dspec in self.done_specs.all():
            total += 1
            completades += dspec.fraccio
        if total == 0:
            return "-"
        return "{:.1f} ({:.1f}%)".format(
            completades, round(100 * completades / total, 1)
        )

    def hores_completades(self):
        total = 0
        completades = 0.0
        for dspec in self.done_specs.all():
            hores = dspec.spec.hores_estimades or 0
            total += hores
            completades += hores * dspec.fraccio
        if total == 0:
            return "-"
        return "{:.1f} ({:.1f}%)".format(
            completades, round(100 * completades / total, 1)
        )

    def _dades_mps_sprint(self):
        """Agrupa les specs del sprint per mòdul professional.

        Es tenen en compte totes les specs del sprint, encara que la
        qualificació no tingui encara un DoneSpec per a elles (per exemple,
        si la spec s'ha afegit després de crear la qualificació).
        """
        done_specs_by_spec = {
            dspec.spec_id: dspec
            for dspec in self.done_specs.prefetch_related("percentatges_mp")
        }
        mps = {}
        for spec in self.sprint.specs.all():
            hores = spec.hores_estimades or 0
            done_spec = done_specs_by_spec.get(spec.id)
            for mp in spec.mp.all():
                if mp.id not in mps:
                    mps[mp.id] = {
                        "obj": mp,
                        "total": 0,
                        "done": 0,
                        "specs_total": 0,
                        "specs_done": 0,
                    }
                fraccio = done_spec.fraccio_per_mp(mp) if done_spec else 0
                mps[mp.id]["total"] += hores
                mps[mp.id]["done"] += hores * fraccio
                mps[mp.id]["specs_total"] += 1
                mps[mp.id]["specs_done"] += fraccio
        return mps

    def percentatges_mps(self):
        """Retorna el percentatge completat de cada mòdul del sprint.

        El percentatge es pondera per les hores estimades de les specs.
        S'inclouen tots els mòduls amb specs al sprint, fins i tot els que
        encara no tenen cap spec completada.
        """
        resultat = []
        for dades in self._dades_mps_sprint().values():
            percentatge = (
                100 * dades["done"] / dades["total"] if dades["total"] else 0
            )
            resultat.append(
                {
                    "obj": dades["obj"],
                    "mp": dades["obj"],
                    "nom": dades["obj"].nom,
                    "total": dades["total"],
                    "done": round(dades["done"], 2),
                    "specs_total": dades["specs_total"],
                    "specs_done": round(dades["specs_done"], 2),
                    "percentatge": round(percentatge, 1),
                    "percentatge_text": "{:.1f}".format(percentatge),
                }
            )
        return sorted(resultat, key=lambda d: (d["obj"].numero, d["obj"].nom))

    def specs_completades_mps(self):
        ret = ""
        for dades in self.percentatges_mps():
            if dades["specs_total"]:
                ret += "{} : {:.1f}/{:.0f} ({:.1f}%)<br>".format(
                    dades["nom"],
                    dades["specs_done"],
                    dades["specs_total"],
                    round(
                        100 * dades["specs_done"] / dades["specs_total"], 1
                    ),
                )
        return mark_safe(ret)

    def specs_completades_mps_ponderat(self):
        ret = ""
        for dades in self.percentatges_mps():
            ret += "{} : {:.1f}%<br>".format(
                dades["nom"], dades["percentatge"]
            )
        return mark_safe(ret)

    def hores_completades_per_mps(self):
        return self._dades_mps_sprint()


class DoneSpec(models.Model):
    """Percentatge de compleció d'una spec dins d'una qualificació."""

    class Meta:
        verbose_name = "spec completada"
        verbose_name_plural = "specs completades"
        ordering = ["spec__ordre", "spec__id"]
        constraints = [
            models.UniqueConstraint(
                fields=["qualificacio", "spec"],
                name="unique_donespec_qualificacio_spec",
            )
        ]

    qualificacio = models.ForeignKey(
        Qualificacio, on_delete=models.CASCADE, related_name="done_specs"
    )
    spec = models.ForeignKey(Spec, on_delete=models.CASCADE, related_name="done_specs")
    percentatge = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="percentatge de compleció",
    )
    qualificacio_individual = models.BooleanField(
        default=False,
        verbose_name="qualificació individual per mòdul professional",
    )

    def __str__(self):
        return "{} : {} ({:.1f}%)".format(
            self.spec.ordre, self.spec.nom, self.percentatge
        )

    @property
    def ordre(self):
        return self.spec.ordre

    @property
    def fraccio(self):
        return min(max(self.percentatge or 0, 0), 100) / 100

    def fraccio_per_mp(self, mp):
        if not self.qualificacio_individual:
            return self.fraccio
        for percentatge in self.percentatges_mp.all():
            if percentatge.mp_id == mp.id:
                return percentatge.fraccio
        return self.fraccio


class DoneSpecPercentatgeMP(models.Model):
    """Percentatge de compleció d'un MP dins d'una spec qualificada."""

    class Meta:
        verbose_name = "percentatge de mòdul professional"
        verbose_name_plural = "percentatges de mòduls professionals"
        ordering = ["mp__numero", "mp__nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["done_spec", "mp"],
                name="unique_donespec_percentatge_mp",
            )
        ]

    done_spec = models.ForeignKey(
        DoneSpec,
        on_delete=models.CASCADE,
        related_name="percentatges_mp",
    )
    mp = models.ForeignKey(
        ModulProfessional,
        on_delete=models.CASCADE,
        related_name="percentatges_done_spec",
    )
    percentatge = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="percentatge de compleció",
    )

    def __str__(self):
        return "{} : {} ({:.1f}%)".format(
            self.done_spec.spec.nom, self.mp.nom, self.percentatge
        )

    @property
    def fraccio(self):
        return min(max(self.percentatge or 0, 0), 100) / 100


class SpecFeedback(models.Model):
    """Comentari o registre d'hores reals sobre una spec."""

    class Meta:
        verbose_name = "comentari de spec"
        verbose_name_plural = "comentaris de specs"
        ordering = ["-data"]

    spec = models.ForeignKey(
        Spec, on_delete=models.CASCADE, related_name="feedbacks"
    )
    usuari = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedbacks",
    )
    equip = models.ForeignKey(
        Equip,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedbacks",
    )
    data = models.DateTimeField(default=timezone.now)
    hores = models.FloatField(null=True, blank=True)
    desc = models.TextField(blank=True)

    def __str__(self):
        return "{} - {}".format(self.spec, self.data)
