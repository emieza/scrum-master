import datetime
import io
from unittest.mock import Mock

from allauth.account.models import EmailAddress
from django.test import TestCase, override_settings
from django.urls import reverse
from django_ckeditor_5.widgets import CKEditor5Widget
from odf import teletype
from odf.opendocument import load
from odf.table import Table, TableCell, TableRow

from .adapters import SocialAccountAdapter
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
    Sprint,
    User,
)


def _llegeix_ods(contingut):
    document = load(io.BytesIO(contingut))
    fulls = {}
    for table in document.spreadsheet.getElementsByType(Table):
        files = []
        for row in table.getElementsByType(TableRow):
            valors = []
            for cell in row.getElementsByType(TableCell):
                valor = cell.getAttribute("value")
                if valor is not None:
                    valors.append(float(valor))
                else:
                    valors.append(teletype.extractText(cell))
            files.append(valors)
        fulls[table.getAttribute("name")] = files
    return fulls


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

    def test_pagina_entrada(self):
        response = self.client.get(reverse("account_login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Entra al portal")
        self.assertContains(response, 'name="login"')

    def test_login_amb_email_amb_allauth(self):
        response = self.client.post(
            reverse("account_login"),
            {"login": "profe@example.cat", "password": "contrasenya123"},
        )
        self.assertRedirects(response, reverse("home"))

    def test_registre_amb_email_qualsevol(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "alumne@example.com",
                "password1": "contrasenya-segura-123",
                "password2": "contrasenya-segura-123",
            },
        )
        self.assertRedirects(response, reverse("home"))
        user = User.objects.get(email="alumne@example.com")
        self.assertTrue(user.username)
        self.assertTrue(user.check_password("contrasenya-segura-123"))
        self.assertTrue(
            EmailAddress.objects.filter(
                user=user, email="alumne@example.com"
            ).exists()
        )
        self.assertEqual(
            self.client.session["_auth_user_id"], str(user.pk)
        )

    @override_settings(
        SOCIALACCOUNT_PROVIDERS={
            "google": {"APP": {"client_id": "google-id", "secret": "google-secret"}},
            "microsoft": {
                "APP": {"client_id": "microsoft-id", "secret": "microsoft-secret"}
            },
            "github": {"APP": {"client_id": "github-id", "secret": "github-secret"}},
        }
    )
    def test_pagina_entrada_mostra_proveidors_configurats(self):
        response = self.client.get(reverse("account_login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Continua amb Google")
        self.assertContains(response, "Continua amb Microsoft")
        self.assertContains(response, "Continua amb GitHub")

    @override_settings(SOCIALACCOUNT_PROVIDERS={})
    def test_pagina_entrada_amaga_proveidors_no_configurats(self):
        response = self.client.get(reverse("account_login"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Continua amb Google")
        self.assertNotContains(response, "Continua amb Microsoft")
        self.assertNotContains(response, "Continua amb GitHub")

    def test_social_login_connecta_amb_email_verificat(self):
        address = EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=False,
        )
        verified_address = Mock(email=self.user.email, verified=True)
        sociallogin = Mock(
            is_existing=False,
            email_addresses=[verified_address],
        )
        SocialAccountAdapter().pre_social_login(None, sociallogin)
        address.refresh_from_db()
        self.assertTrue(address.verified)
        sociallogin.connect.assert_called_once_with(None, self.user)

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

    def test_targetes_qualificacio_mostren_percentatges_per_mp(self):
        equip = Equip.objects.create(nom="Equip Alpha", projecte=self.projecte)
        quali = Qualificacio.objects.create(equip=equip, sprint=self.sprint)
        done_spec = DoneSpec.objects.create(
            qualificacio=quali, spec=self.spec, done=True
        )
        self.assertTrue(done_spec.done)
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("qualifica"), {"projecte_id": self.projecte.id}
        )
        self.assertContains(response, "Equip Alpha")
        self.assertContains(response, "<th>Mòdul professional</th>")
        self.assertContains(response, "<th>Hores planificades</th>")
        self.assertContains(response, "<th>Hores completades</th>")
        self.assertContains(response, "<th>Percentatge</th>")
        self.assertContains(response, str(self.mp))
        self.assertContains(response, "<td>8,0</td>", count=2)
        self.assertContains(response, "<td>100.0%</td>")

    def test_percentatges_mps_inclou_specs_afegides_despres(self):
        equip = Equip.objects.create(nom="Equip Alpha", projecte=self.projecte)
        quali = Qualificacio.objects.create(equip=equip, sprint=self.sprint)
        DoneSpec.objects.create(qualificacio=quali, spec=self.spec, done=True)
        mp_pendent = ModulProfessional.objects.create(
            numero=7, nom="Desenvolupament web en entorn servidor", cicle=self.cicle
        )
        spec_pendent = Spec.objects.create(
            nom="API", projecte=self.projecte, ordre=2, hores_estimades=2
        )
        spec_pendent.mp.add(mp_pendent)
        spec_pendent.sprints.add(self.sprint)
        dades = {d["nom"]: d for d in quali.percentatges_mps()}
        self.assertEqual(dades[self.mp.nom]["percentatge"], 100.0)
        self.assertEqual(dades[mp_pendent.nom]["percentatge"], 0.0)
        self.assertEqual(dades[mp_pendent.nom]["specs_done"], 0)

    def test_exportacio_ods_separa_els_moduls_en_fulls(self):
        equip = Equip.objects.create(nom="Equip Alpha", projecte=self.projecte)
        equip.membres.add(self.user)
        quali1 = Qualificacio.objects.create(equip=equip, sprint=self.sprint)
        DoneSpec.objects.create(
            qualificacio=quali1, spec=self.spec, done=True
        )
        sprint2 = Sprint.objects.create(
            nom="Sprint 2",
            projecte=self.projecte,
            inici=datetime.date.today() + datetime.timedelta(days=7),
            final=datetime.date.today() + datetime.timedelta(days=14),
        )
        spec2 = Spec.objects.create(
            nom="Tancament de sessió",
            projecte=self.projecte,
            ordre=2,
            hores_estimades=2,
        )
        spec2.mp.add(self.mp)
        spec2.sprints.add(sprint2)
        quali2 = Qualificacio.objects.create(equip=equip, sprint=sprint2)
        DoneSpec.objects.create(
            qualificacio=quali2, spec=spec2, done=False
        )
        mp2 = ModulProfessional.objects.create(
            numero=7,
            nom="Desenvolupament web en entorn servidor",
            cicle=self.cicle,
        )
        spec3 = Spec.objects.create(
            nom="API",
            projecte=self.projecte,
            ordre=3,
            hores_estimades=4,
        )
        spec3.mp.add(mp2)
        spec3.sprints.add(self.sprint)
        DoneSpec.objects.create(
            qualificacio=quali1, spec=spec3, done=True
        )

        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("descarrega_qualificacions", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.oasis.opendocument.spreadsheet",
        )
        self.assertIn(".ods", response["Content-Disposition"])
        fulls = _llegeix_ods(response.content)
        self.assertEqual(
            set(fulls), {self.mp.nom[:31], mp2.nom[:31]}
        )

        full = fulls[self.mp.nom[:31]]
        self.assertEqual(
            full[0],
            [
                "Cognoms",
                "Nom",
                "Email",
                "Equip",
                "Sprint 1 - Hores planificades",
                "Sprint 1 - Hores completades",
                "Sprint 1 - Percentatge",
                "Sprint 2 - Hores planificades",
                "Sprint 2 - Hores completades",
                "Sprint 2 - Percentatge",
                "Hores totals",
                "Hores completades",
                "Percentatge total",
            ],
        )
        self.assertEqual(
            full[1],
            [
                "",
                "",
                self.user.email,
                equip.nom,
                8,
                8,
                "100.0%",
                2,
                0,
                "0.0%",
                10,
                8,
                "80.0%",
            ],
        )

        full2 = fulls[mp2.nom[:31]]
        self.assertEqual(full2[1][4], 4)
        self.assertEqual(full2[1][5], 4)
        self.assertEqual(full2[1][6], "100.0%")
        self.assertEqual(full2[1][10], 4)
        self.assertEqual(full2[1][11], 4)
        self.assertEqual(full2[1][12], "100.0%")

    def test_noms_de_full_ods_son_valids_i_unics(self):
        for numero in (8, 9):
            ModulProfessional.objects.create(
                numero=numero,
                nom="Mòdul amb un nom molt llarg per provar els fulls",
                cicle=self.cicle,
            )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("descarrega_qualificacions", args=[self.projecte.id])
        )
        noms = list(_llegeix_ods(response.content))
        self.assertEqual(len(noms), len(set(noms)))
        self.assertTrue(all(len(nom) <= 31 for nom in noms))

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
        self.assertContains(response, "django_ckeditor_5")
        self.assertContains(response, "django_ckeditor_5/dist/bundle.js")
        self.assertContains(response, "django_ckeditor_5/dist/styles.css")

    def test_descripcions_amb_editor_enriquit(self):
        self.assertIsInstance(
            Projecte._meta.get_field("descripcio").formfield().widget,
            CKEditor5Widget,
        )
        self.assertIsInstance(
            Spec._meta.get_field("descripcio").formfield().widget,
            CKEditor5Widget,
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
