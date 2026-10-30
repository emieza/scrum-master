import datetime

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from scrum.models import (
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
    User,
)


class Command(BaseCommand):
    help = "Crea dades d'exemple per provar el portal Scrum Master."

    def handle(self, *args, **options):
        groups = {}
        for name in ("alumnes", "profes"):
            groups[name], _ = Group.objects.get_or_create(name=name)

        familia, _ = Categoria.objects.get_or_create(
            nom="Informàtica i comunicacions",
            defaults={"descripcio": "Família professional d'informàtica."},
        )

        cicle, _ = Cicle.objects.get_or_create(
            codi="DAW",
            defaults={
                "nom": "Desenvolupament d'aplicacions web",
                "grau": "CFGS",
                "familia": familia,
                "descripcio": "Cicle formatiu de grau superior de desenvolupament web.",
            },
        )

        centre, _ = Centre.objects.get_or_create(
            nom="Institut Esteve Terradas i Illa",
            defaults={
                "direccio": "Av. de la Generalitat, s/n",
                "poblacio": "Cornellà de Llobregat",
                "cp": "08940",
                "telefon": "934740000",
                "codi": 80001,
                "email": "info@esteveterradas.cat",
                "web": "https://www.esteveterradas.cat",
                "descripcio": "Centre educatiu d'exemple.",
            },
        )
        centre.cicles.add(cicle)

        moduls = []
        for numero, nom in (
            (6, "Desenvolupament web en entorn client"),
            (7, "Desenvolupament web en entorn servidor"),
            (8, "Desplegament d'aplicacions web"),
        ):
            mp, _ = ModulProfessional.objects.get_or_create(
                cicle=cicle,
                numero=numero,
                defaults={"nom": nom, "descripcio": "Mòdul professional d'exemple."},
            )
            moduls.append(mp)

        admin, created = User.objects.get_or_create(
            email="admin@scrummaster.local",
            defaults={
                "username": "admin",
                "first_name": "Admin",
                "last_name": "Scrum",
                "is_staff": True,
                "is_superuser": True,
                "centre": centre,
            },
        )
        if created:
            admin.set_password("admin12345")
            admin.save()

        profe, created = User.objects.get_or_create(
            email="profe@scrummaster.local",
            defaults={
                "username": "profe",
                "first_name": "Marta",
                "last_name": "Professora",
                "centre": centre,
            },
        )
        if created:
            profe.set_password("profe12345")
            profe.save()
        profe.groups.add(groups["profes"])
        centre.admins.add(profe, admin)

        alumnes = []
        for index, (nom, cognom) in enumerate(
            (("Laia", "Alumna"), ("Pau", "Estudiant"), ("Nil", "Programador")), start=1
        ):
            alumne, created = User.objects.get_or_create(
                email="alumne{}@scrummaster.local".format(index),
                defaults={
                    "username": "alumne{}".format(index),
                    "first_name": nom,
                    "last_name": cognom,
                    "centre": centre,
                },
            )
            if created:
                alumne.set_password("alumne12345")
                alumne.save()
            alumne.groups.add(groups["alumnes"])
            alumnes.append(alumne)

        projecte, _ = Projecte.objects.get_or_create(
            nom="Aplicació del Penjat",
            defaults={
                "descripcio": (
                    "<p>Desenvolupament d'una aplicació web per jugar al penjat "
                    "amb diferents nivells de dificultat.</p>"
                ),
                "centre": centre,
                "cicle": cicle,
                "inici": datetime.date.today() - datetime.timedelta(days=20),
                "final": datetime.date.today() + datetime.timedelta(days=20),
            },
        )
        projecte.admins.add(profe)

        sprint1, _ = Sprint.objects.get_or_create(
            projecte=projecte,
            nom="Sprint 1 · Fonaments",
            defaults={
                "inici": datetime.date.today() - datetime.timedelta(days=20),
                "final": datetime.date.today() - datetime.timedelta(days=6),
                "notes": "Primera iteració del projecte.",
            },
        )
        sprint2, _ = Sprint.objects.get_or_create(
            projecte=projecte,
            nom="Sprint 2 · Joc i puntuació",
            defaults={
                "inici": datetime.date.today() - datetime.timedelta(days=5),
                "final": datetime.date.today() + datetime.timedelta(days=9),
                "notes": "Segona iteració del projecte.",
            },
        )

        specs_data = [
            (
                1,
                "Pantalla d'inici i selecció de dificultat",
                "L'usuari pot triar el nivell de dificultat abans de començar.",
                [moduls[0]],
                8.0,
                [sprint1],
            ),
            (
                2,
                "Gestió de paraules i categories",
                "El servidor subministra paraules segons la categoria triada.",
                [moduls[1]],
                12.0,
                [sprint1],
            ),
            (
                3,
                "Lògica del joc del penjat",
                "Es validen les lletres encertades i les vides restants.",
                [moduls[0], moduls[1]],
                16.0,
                [sprint2],
            ),
            (
                4,
                "Puntuacions i rànquing",
                "Es desen les puntuacions i es mostra un rànquing.",
                [moduls[1]],
                10.0,
                [sprint2],
            ),
            (
                5,
                "Desplegament de l'aplicació",
                "L'aplicació queda publicada en un entorn de proves.",
                [moduls[2]],
                6.0,
                [sprint2],
            ),
        ]
        specs = []
        for ordre, nom, descripcio, mps, hores, sprints in specs_data:
            spec, _ = Spec.objects.get_or_create(
                projecte=projecte,
                ordre=ordre,
                defaults={
                    "nom": nom,
                    "descripcio": "<p>{}</p>".format(descripcio),
                    "hores_estimades": hores,
                },
            )
            spec.mp.set(mps)
            spec.sprints.set(sprints)
            specs.append(spec)

        equip, _ = Equip.objects.get_or_create(
            projecte=projecte,
            nom="Equip Alpha",
            defaults={"descripcio": "Equip d'exemple del projecte."},
        )
        equip.membres.set(alumnes)

        qualificacio, _ = Qualificacio.objects.get_or_create(
            equip=equip, sprint=sprint1
        )
        for spec in sprint1.specs.all():
            DoneSpec.objects.get_or_create(
                qualificacio=qualificacio, spec=spec, defaults={"done": True}
            )

        SpecFeedback.objects.get_or_create(
            spec=specs[0],
            usuari=alumnes[0],
            equip=equip,
            defaults={
                "hores": 7.5,
                "desc": "<p>Hem acabat la pantalla d'inici i la selecció de dificultat.</p>",
            },
        )

        self.stdout.write(self.style.SUCCESS("Dades d'exemple creades correctament."))
        self.stdout.write("Superusuari: admin@scrummaster.local / admin12345")
        self.stdout.write("Professor: profe@scrummaster.local / profe12345")
        self.stdout.write("Alumne: alumne1@scrummaster.local / alumne12345")
