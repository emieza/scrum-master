import datetime

from django.test import TestCase
from django.urls import reverse
from djrichtextfield.widgets import RichTextWidget

from .models import (
    Categoria,
    Centre,
    Cicle,
    ModulProfessional,
    Projecte,
    Spec,
    Sprint,
    User,
)


class ScrumTests(TestCase):
    def setUp(self):
        self.familia = Categoria.objects.create(nom="Informàtica")
        self.cicle = Cicle.objects.create(
            grau="CFGS", codi="DAW", nom="Desenvolupament d'aplicacions web"
        )
        self.centre = Centre.objects.create(
            nom="Institut Exemple",
            poblacio="Barcelona",
            cp="08001",
            email="info@example.cat",
        )
        self.user = User.objects.create_user(
            username="profe",
            email="profe@example.cat",
            password="contrasenya123",
        )
        self.projecte = Projecte.objects.create(
            nom="Projecte de prova",
            descripcio="<p>Descripció</p>",
            centre=self.centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        self.projecte.admins.add(self.user)
        self.sprint = Sprint.objects.create(
            nom="Sprint 1",
            projecte=self.projecte,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=7),
        )
        self.mp = ModulProfessional.objects.create(
            numero=6, nom="Desenvolupament web en entorn client", cicle=self.cicle
        )
        self.spec = Spec.objects.create(
            nom="Pantalla d'inici",
            projecte=self.projecte,
            ordre=1,
            hores_estimades=8,
        )
        self.spec.mp.add(self.mp)
        self.spec.sprints.add(self.sprint)

    def test_llista_projectes(self):
        response = self.client.get(reverse("projectes"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Projecte de prova")

    def test_detall_projecte(self):
        response = self.client.get(reverse("projecte", args=[self.projecte.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pantalla d&#x27;inici")
        self.assertContains(response, "Sprint 1")

    def test_hores_sprint(self):
        self.assertEqual(self.sprint.hores, 8)
        dades = self.sprint.dades_mps()
        self.assertEqual(dades[self.mp.nom]["specs"], 1)
        self.assertEqual(dades[self.mp.nom]["hores"], 8)

    def test_login_amb_email(self):
        self.assertTrue(
            self.client.login(
                username="profe@example.cat", password="contrasenya123"
            )
        )

    def test_qualifica_requereix_login(self):
        response = self.client.get(reverse("qualifica"))
        self.assertEqual(response.status_code, 302)

    def test_qualifica_projecte_propi(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("qualifica"), {"projecte_id": self.projecte.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Projecte de prova")

    def test_admin_projecte_te_boto_per_colapsar_specs(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("admin:scrum_projecte_change", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Col·lapsa totes les specs")
        self.assertContains(response, "js/admin_collapse_specs.js")
        self.assertContains(response, "css/admin_collapse_specs.css")
        self.assertContains(response, 'id="id_specs-0-descripcio"')

    def test_admin_projecte_descripcio_amb_editor_enriquit(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("admin:scrum_projecte_change", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_descripcio"')
        self.assertContains(response, "djrichtextfield")
        self.assertContains(response, "ckeditor.js")
        self.assertContains(response, reverse("djrichtextfield_init"))
        init = self.client.get(reverse("djrichtextfield_init"))
        self.assertEqual(init.status_code, 200)
        self.assertContains(init, "CKEDITOR.replace")

    def test_descripcions_amb_editor_enriquit(self):
        self.assertIsInstance(
            Projecte._meta.get_field("descripcio").formfield().widget,
            RichTextWidget,
        )
        self.assertIsInstance(
            Spec._meta.get_field("descripcio").formfield().widget,
            RichTextWidget,
        )

    def test_autocomplete_sprints_filtrat_per_projecte(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        altre_projecte = Projecte.objects.create(
            nom="Altre projecte",
            centre=self.centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        Sprint.objects.create(
            nom="Sprint extern",
            projecte=altre_projecte,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=7),
        )
        response = self.client.get(
            reverse("admin:autocomplete"),
            {
                "app_label": "scrum",
                "model_name": "spec",
                "field_name": "sprints",
                "term": "Sprint",
                "projecte_id": self.projecte.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        textos = [resultat["text"] for resultat in response.json()["results"]]
        self.assertIn("Sprint 1", textos)
        self.assertNotIn("Sprint extern", textos)
