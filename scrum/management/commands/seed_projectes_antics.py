import datetime
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from scrum.models import (
    Categoria,
    Centre,
    Cicle,
    Equip,
    ModulProfessional,
    Projecte,
    Spec,
    Sprint,
)


class Command(BaseCommand):
    help = (
        "Carrega els projectes antics del portal Scrum de l'IETI, amb els seus "
        "sprints, specs, equips i vídeos."
    )

    CICLES_SENSE_MODULS_NOUS = {"ICB0", "ICC0"}
    CONNECTORS_NOM_MODUL = {
        "a",
        "al",
        "als",
        "amb",
        "d",
        "de",
        "del",
        "el",
        "els",
        "en",
        "i",
        "la",
        "les",
        "per",
    }

    @staticmethod
    def _normalitza_codi(codi):
        codi = codi.strip()
        match = re.match(r"^([A-Za-z]+)(\d+)$", codi)
        if match:
            return match.group(1).lower() + str(int(match.group(2)))
        return codi.lower()

    @staticmethod
    def _normalitza_nom_modul(nom):
        nom = unicodedata.normalize("NFKD", nom or "")
        nom = "".join(char for char in nom if not unicodedata.combining(char))
        nom = nom.casefold().replace("’", " ").replace("'", " ")
        nom = re.sub(r"[^a-z0-9]+", " ", nom)
        return re.sub(r"\s+", " ", nom).strip()

    @classmethod
    def _inicials_modul(cls, nom):
        paraules = cls._normalitza_nom_modul(nom).split()
        return "".join(
            paraula[0]
            for paraula in paraules
            if paraula not in cls.CONNECTORS_NOM_MODUL
        )

    @classmethod
    def _similitud_noms_modul(cls, nom_a, nom_b):
        nom_a = cls._normalitza_nom_modul(nom_a)
        nom_b = cls._normalitza_nom_modul(nom_b)
        if not nom_a or not nom_b:
            return 0.0
        if nom_a == nom_b:
            return 1.0
        puntuacio = SequenceMatcher(None, nom_a, nom_b).ratio()
        inicials_a = cls._inicials_modul(nom_a)
        if inicials_a and inicials_a == cls._inicials_modul(nom_b):
            puntuacio = max(puntuacio, 0.9)
        return puntuacio

    def _modul_existent_per_similitud(self, cicle, nom):
        millor_modul = None
        millor_puntuacio = 0.0
        for modul in cicle.moduls.order_by("pk"):
            puntuacio = self._similitud_noms_modul(nom, modul.nom)
            if puntuacio > millor_puntuacio:
                millor_modul = modul
                millor_puntuacio = puntuacio
        if millor_puntuacio >= 0.6:
            return millor_modul
        return None

    @staticmethod
    def _data(valor):
        return datetime.date.fromisoformat(valor)

    @staticmethod
    def _separa_centre(valor):
        match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", valor)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return valor.strip(), ""

    def _get_cicle(self, nom, codi, grau, familia):
        cicle = Cicle.objects.filter(nom__iexact=nom).first()
        if cicle is not None:
            return cicle

        familia_obj = None
        if familia:
            familia_obj, _ = Categoria.objects.get_or_create(nom=familia)

        base = (codi or "ALT")[:8]
        candidat = base
        index = 2
        while Cicle.objects.filter(codi=candidat).exists():
            sufix = str(index)
            candidat = base[: 8 - len(sufix)] + sufix
            index += 1

        return Cicle.objects.create(
            codi=candidat,
            nom=nom,
            grau=grau,
            familia=familia_obj,
        )

    def _get_centre(self, valor):
        nom, poblacio = self._separa_centre(valor)
        centre = Centre.objects.filter(nom__iexact=nom).first()
        if centre is not None:
            return centre
        return Centre.objects.create(
            nom=nom,
            poblacio=poblacio,
            cp="",
            email="",
        )

    def _get_modul(self, cicle, modul, cache):
        clau = (cicle.pk, self._normalitza_codi(modul["codi"]))
        if clau in cache:
            return cache[clau]

        mp = ModulProfessional.objects.filter(
            cicle=cicle, nom__iexact=modul["nom"]
        ).first()
        if mp is None:
            mp = ModulProfessional.objects.filter(
                cicle=cicle, numero=modul["numero"], nom__iexact=modul["nom"]
            ).first()
        if mp is None:
            if cicle.codi.upper() in self.CICLES_SENSE_MODULS_NOUS:
                mp = self._modul_existent_per_similitud(cicle, modul["nom"])
            else:
                mp = ModulProfessional.objects.create(
                    cicle=cicle,
                    numero=modul["numero"],
                    nom=modul["nom"],
                )

        cache[clau] = mp
        return mp

    def _resol_modul(self, cicle, codi, moduls, cache):
        codi_norm = self._normalitza_codi(codi)
        for modul, mp in moduls:
            if self._normalitza_codi(modul["codi"]) == codi_norm:
                return mp
        for modul, mp in moduls:
            modul_norm = self._normalitza_codi(modul["codi"])
            if modul_norm.startswith(codi_norm) or codi_norm.startswith(modul_norm):
                return mp

        digits = re.search(r"\d+", codi)
        modul = {
            "codi": codi,
            "numero": int(digits.group()) if digits else 0,
            "nom": codi,
        }
        return self._get_modul(cicle, modul, cache)

    def handle(self, *args, **options):
        data_path = Path(__file__).with_name("projectes_antics.json")
        data = json.loads(data_path.read_text(encoding="utf-8"))

        stats = {
            "projectes": 0,
            "sprints": 0,
            "specs": 0,
            "equips": 0,
            "videos": 0,
        }

        with transaction.atomic():
            modul_cache = {}
            projectes_per_site = {}

            for projecte_data in data["projectes"]:
                cicle = self._get_cicle(
                    projecte_data["cicle"],
                    projecte_data["cicle_codi"],
                    projecte_data["cicle_grau"],
                    projecte_data["cicle_familia"],
                )
                centre = self._get_centre(projecte_data["centre"])
                centre.cicles.add(cicle)

                inici = self._data(projecte_data["inici"])
                final = self._data(projecte_data["final"])
                projecte = Projecte.objects.filter(
                    nom=projecte_data["nom"], centre=centre
                ).first()
                if projecte is None:
                    projecte = Projecte.objects.create(
                        nom=projecte_data["nom"],
                        centre=centre,
                        descripcio=projecte_data["descripcio"],
                        cicle=cicle,
                        inici=inici,
                        final=final,
                    )
                    stats["projectes"] += 1
                else:
                    projecte.descripcio = projecte_data["descripcio"]
                    projecte.cicle = cicle
                    projecte.inici = inici
                    projecte.final = final
                    projecte.save(
                        update_fields=["descripcio", "cicle", "inici", "final"]
                    )
                projectes_per_site[projecte_data["site_id"]] = projecte

                moduls = []
                for modul_data in projecte_data["moduls"]:
                    mp = self._get_modul(cicle, modul_data, modul_cache)
                    moduls.append((modul_data, mp))

                sprints = {}
                for sprint_data in projecte_data["sprints"]:
                    sprint, created = Sprint.objects.update_or_create(
                        projecte=projecte,
                        nom=sprint_data["nom"],
                        defaults={
                            "inici": self._data(sprint_data["inici"]),
                            "final": self._data(sprint_data["final"]),
                        },
                    )
                    sprints[sprint_data["anchor"]] = sprint
                    if created:
                        stats["sprints"] += 1

                for spec_data in projecte_data["specs"]:
                    spec, created = Spec.objects.update_or_create(
                        projecte=projecte,
                        ordre=spec_data["ordre"],
                        nom=spec_data["nom"],
                        defaults={
                            "descripcio": spec_data["descripcio"],
                            "hores_estimades": spec_data["hores"],
                        },
                    )
                    if created:
                        stats["specs"] += 1

                    mps = [
                        mp
                        for mp in (
                            self._resol_modul(cicle, codi, moduls, modul_cache)
                            for codi in spec_data["mps"]
                        )
                        if mp is not None
                    ]
                    spec.mp.set(mps)
                    spec.sprints.set(
                        [sprints[anchor] for anchor in spec_data["sprints"]]
                    )

            for video_data in data["videos"]:
                projecte = projectes_per_site.get(video_data["site_projecte_id"])
                if projecte is None:
                    continue
                nom = video_data["equip"][:255]
                equip = Equip.objects.filter(
                    projecte=projecte, nom=nom
                ).first()
                if equip is None:
                    Equip.objects.create(
                        projecte=projecte,
                        nom=nom,
                        link_video=video_data["link"],
                    )
                    stats["equips"] += 1
                    stats["videos"] += 1
                else:
                    equip.link_video = video_data["link"]
                    equip.save(update_fields=["link_video"])

        self.stdout.write(
            self.style.SUCCESS(
                "Projectes antics carregats: {} projectes, {} sprints, {} specs, "
                "{} equips i {} vídeos.".format(
                    stats["projectes"],
                    stats["sprints"],
                    stats["specs"],
                    stats["equips"],
                    stats["videos"],
                )
            )
        )
