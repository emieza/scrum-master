import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from scrum.models import Categoria, Cicle, ModulProfessional


class Command(BaseCommand):
    help = (
        "Insereix o actualitza els cicles formatius (CFGB, CFGM i CFGS), els cursos "
        "d'especialització i els mòduls professionals 2024/2025 i posteriors."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra el resultat sense desar cap canvi a la base de dades.",
        )

    @staticmethod
    def module_numero(codi):
        return int("".join(char for char in codi if char.isdigit()))

    def handle(self, *args, **options):
        data_path = Path(__file__).with_name("cicles_i_mps_2026.json")
        data = json.loads(data_path.read_text(encoding="utf-8"))

        stats = {
            "categories_created": 0,
            "cicles_created": 0,
            "cicles_updated": 0,
            "modules_created": 0,
            "modules_updated": 0,
        }

        with transaction.atomic():
            for cicle_data in data["cicles"] + data.get("especialitzacions", []):
                familia, familia_created = Categoria.objects.get_or_create(
                    nom=cicle_data["familia"]
                )
                if familia_created:
                    stats["categories_created"] += 1

                cicle = Cicle.objects.filter(codi=cicle_data["codi"]).first()
                if cicle is None:
                    cicle = Cicle.objects.filter(nom__iexact=cicle_data["nom"]).first()
                    if cicle is not None:
                        self.stdout.write(
                            self.style.WARNING(
                                "Cicle existent amb codi {} per a {}; es conserva el codi.".format(
                                    cicle.codi, cicle.nom
                                )
                            )
                        )

                if cicle is None:
                    cicle = Cicle.objects.create(
                        codi=cicle_data["codi"],
                        nom=cicle_data["nom"],
                        grau=cicle_data["grau"],
                        familia=familia,
                        pladestudis=cicle_data["pladestudis"],
                    )
                    stats["cicles_created"] += 1
                else:
                    cicle.nom = cicle_data["nom"]
                    cicle.grau = cicle_data["grau"]
                    cicle.familia = familia
                    cicle.pladestudis = cicle_data["pladestudis"]
                    cicle.save(
                        update_fields=["nom", "grau", "familia", "pladestudis"]
                    )
                    stats["cicles_updated"] += 1

                for module_data in cicle_data["moduls"]:
                    _, module_created = ModulProfessional.objects.update_or_create(
                        cicle=cicle,
                        numero=self.module_numero(module_data["codi"]),
                        defaults={"nom": module_data["nom"]},
                    )
                    if module_created:
                        stats["modules_created"] += 1
                    else:
                        stats["modules_updated"] += 1

            if options["dry_run"]:
                transaction.set_rollback(True)

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                "{}Categories: {} creades | Cicles: {} creats, {} actualitzats | "
                "Mòduls: {} creats, {} actualitzats".format(
                    prefix,
                    stats["categories_created"],
                    stats["cicles_created"],
                    stats["cicles_updated"],
                    stats["modules_created"],
                    stats["modules_updated"],
                )
            )
        )
        for omes in data.get("omessos", []):
            self.stdout.write(
                self.style.WARNING(
                    "{}Omesa: {} ({})".format(prefix, omes["etiqueta"], omes["motiu"])
                )
            )
