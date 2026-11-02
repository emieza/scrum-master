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
    DoneSpecPercentatgeMP,
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

    def test_llista_projectes_anonima_no_mostra_go_ni_clonar(self):
        response = self.client.get(reverse("projectes"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Go!")
        self.assertNotContains(response, "Clonar")

    def test_llista_projectes_filtra_pel_nom_del_projecte(self):
        Projecte.objects.create(
            nom="Projecte d'altra cosa",
            centre=self.centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        response = self.client.get(reverse("projectes"), {"nom": "PROVA"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Projecte de prova")
        self.assertNotContains(response, "Projecte d&#x27;altra cosa")

    def test_llista_projectes_filtra_pel_centre_educatiu(self):
        altre_centre = Centre.objects.create(
            nom="Institut Altre",
            poblacio="Tarragona",
            cp="43001",
            email="altre@example.cat",
        )
        Projecte.objects.create(
            nom="Projecte d'un altre centre",
            centre=altre_centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        response = self.client.get(reverse("projectes"), {"centre": "Altre"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Projecte d&#x27;un altre centre")
        self.assertNotContains(response, "Projecte de prova")

    def test_llista_projectes_filtra_pel_nom_del_cicle(self):
        altre_cicle = Cicle.objects.create(
            grau="CFGM", codi="SMX", nom="Sistemes microinformàtics"
        )
        Projecte.objects.create(
            nom="Projecte de sistemes",
            centre=self.centre,
            cicle=altre_cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        response = self.client.get(reverse("projectes"), {"cicle": "micro"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Projecte de sistemes")
        self.assertNotContains(response, "Projecte de prova")

    def test_llista_projectes_filtra_per_nom_codi_de_cicle(self):
        altre_cicle = Cicle.objects.create(
            grau="CFGM", codi="SMX", nom="Sistemes microinformàtics"
        )
        Projecte.objects.create(
            nom="Projecte de sistemes",
            centre=self.centre,
            cicle=altre_cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        response = self.client.get(reverse("projectes"), {"cicle": "SMX"})
        self.assertContains(response, "Projecte de sistemes")
        self.assertNotContains(response, "Projecte de prova")

    def test_llista_projectes_filtra_de_forma_general_i_neteja_els_filtres(self):
        altre_centre = Centre.objects.create(
            nom="Institut Altre",
            poblacio="Tarragona",
            cp="43001",
            email="altre@example.cat",
        )
        Projecte.objects.create(
            nom="Projecte d'un altre centre",
            centre=altre_centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        response = self.client.get(reverse("projectes"), {"q": "Altre"})
        self.assertContains(response, "Projecte d&#x27;un altre centre")
        self.assertNotContains(response, "Projecte de prova")
        self.assertContains(response, reverse("projectes"))
        self.assertContains(response, "Neteja els filtres")

        response = self.client.get(reverse("projectes"), {"nom": "inexistent"})
        self.assertContains(
            response, "No hi ha cap projecte que coincideixi amb els filtres."
        )

    def test_llista_projectes_mostra_els_valors_dels_filtres(self):
        response = self.client.get(
            reverse("projectes"),
            {"nom": "prova", "centre": "Exemple", "cicle": "DAW"},
        )
        self.assertContains(response, 'value="prova"')
        self.assertContains(response, 'value="Exemple"')
        self.assertContains(response, 'value="DAW"')

    def test_llista_projectes_loguejada_mostra_el_boto_de_clonar(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("projectes"))
        self.assertContains(response, "Clonar")
        self.assertNotContains(response, "Go!")
        self.assertContains(
            response,
            'data-nom-clon="Projecte de prova (Còpia)"',
        )
        self.assertContains(
            response,
            reverse("clona_projecte", args=[self.projecte.id]),
        )
        self.assertContains(
            response,
            "btn btn-small waves-effect waves-light modal-trigger",
        )

    def test_nom_per_defecte_de_clon_evita_colisions(self):
        Projecte.objects.create(
            nom="Projecte de prova (Còpia)",
            centre=self.centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        Projecte.objects.create(
            nom="Projecte de prova (Còpia 2)",
            centre=self.centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("projectes"))
        self.assertContains(
            response,
            'data-nom-clon="Projecte de prova (Còpia 3)"',
        )

    def test_nom_per_defecte_de_clon_incrementa_el_sufix_de_copia(self):
        Projecte.objects.create(
            nom="Projecte de prova (Còpia)",
            centre=self.centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("projectes"))
        self.assertContains(
            response,
            'data-nom-clon="Projecte de prova (Còpia 2)"',
        )
        self.assertNotContains(
            response,
            "Projecte de prova (Còpia) (Còpia)",
        )

    def test_nom_per_defecte_de_clon_continua_la_numeracio_de_copia(self):
        Projecte.objects.create(
            nom="Projecte de prova (Còpia 2)",
            centre=self.centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("projectes"))
        self.assertContains(
            response,
            'data-nom-clon="Projecte de prova (Còpia 3)"',
        )
        self.assertNotContains(
            response,
            "Projecte de prova (Còpia 2) (Còpia)",
        )

    def test_clona_projecte_requereix_login(self):
        response = self.client.post(
            reverse("clona_projecte", args=[self.projecte.id]),
            {"nom": "Projecte clonat"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response.url)

    def test_clona_projecte_copia_el_projecte_els_sprints_i_les_specs(self):
        self.sprint.notes = "Notes originals"
        self.sprint.save(update_fields=["notes"])
        self.spec.descripcio = "<p>Descripció de la spec</p>"
        self.spec.save(update_fields=["descripcio"])
        sprint_2 = Sprint.objects.create(
            nom="Sprint 2",
            notes="Notes del segon sprint",
            projecte=self.projecte,
            inici=datetime.date.today() + datetime.timedelta(days=10),
            final=datetime.date.today() + datetime.timedelta(days=17),
        )
        spec_2 = Spec.objects.create(
            nom="Spec filla",
            descripcio="<p>Descripció filla</p>",
            pare=self.spec,
            projecte=self.projecte,
            ordre=2,
            hores_estimades=4,
        )
        spec_2.mp.add(self.mp)
        spec_2.sprints.add(sprint_2)
        Equip.objects.create(nom="Equip original", projecte=self.projecte)

        self.client.login(username="profe@example.cat", password="contrasenya123")
        resposta = self.client.post(
            reverse("clona_projecte", args=[self.projecte.id]),
            {"nom": "Projecte clonat"},
        )

        self.assertRedirects(resposta, reverse("els_meus_projectes"))
        clon = Projecte.objects.get(nom="Projecte clonat")
        self.assertEqual(clon.descripcio, self.projecte.descripcio)
        self.assertEqual(clon.centre, self.centre)
        self.assertEqual(clon.cicle, self.cicle)
        self.assertTrue(clon.admins.filter(pk=self.user.pk).exists())
        self.assertEqual(clon.equips.count(), 0)
        self.assertEqual(clon.inici, datetime.date.today())
        self.assertEqual(
            clon.final,
            datetime.date.today() + datetime.timedelta(days=30),
        )

        sprints_clonats = list(clon.sprints.order_by("inici", "id"))
        self.assertEqual([s.nom for s in sprints_clonats], ["Sprint 1", "Sprint 2"])
        self.assertEqual(sprints_clonats[0].notes, "Notes originals")
        self.assertEqual(sprints_clonats[0].inici, datetime.date.today())
        self.assertEqual(
            sprints_clonats[0].final,
            datetime.date.today() + datetime.timedelta(days=7),
        )
        self.assertEqual(
            sprints_clonats[1].inici,
            datetime.date.today() + datetime.timedelta(days=10),
        )
        self.assertEqual(
            sprints_clonats[1].final,
            datetime.date.today() + datetime.timedelta(days=17),
        )
        self.assertEqual(
            sprints_clonats[1].final - sprints_clonats[1].inici,
            datetime.timedelta(days=7),
        )

        specs_clonades = {spec.nom: spec for spec in clon.specs.all()}
        self.assertEqual(set(specs_clonades), {"Pantalla d'inici", "Spec filla"})
        spec_arrel = specs_clonades["Pantalla d'inici"]
        spec_filla = specs_clonades["Spec filla"]
        self.assertEqual(spec_arrel.descripcio, self.spec.descripcio)
        self.assertEqual(spec_arrel.hores_estimades, 8)
        self.assertTrue(spec_arrel.mp.filter(pk=self.mp.pk).exists())
        self.assertEqual(
            list(spec_arrel.sprints.all()),
            [sprints_clonats[0]],
        )
        self.assertEqual(spec_filla.pare, spec_arrel)
        self.assertEqual(spec_filla.hores_estimades, 4)
        self.assertTrue(spec_filla.mp.filter(pk=self.mp.pk).exists())
        self.assertEqual(
            list(spec_filla.sprints.all()),
            [sprints_clonats[1]],
        )

    def test_modal_de_clonar_te_el_reset_d_hores_activat_per_defecte(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("projectes"))
        self.assertContains(
            response,
            'name="reseteja_hores_estimades"',
        )
        self.assertContains(response, 'id="clonar-reseteja-hores" checked')
        self.assertContains(
            response,
            "Reseteja les hores estimades de les specs a zero",
        )

    def test_clona_projecte_reseteja_les_hores_estimades_de_les_specs(self):
        Spec.objects.create(
            nom="Spec amb hores",
            projecte=self.projecte,
            ordre=2,
            hores_estimades=4.5,
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        resposta = self.client.post(
            reverse("clona_projecte", args=[self.projecte.id]),
            {
                "nom": "Projecte sense hores",
                "reseteja_hores_estimades": "on",
            },
        )
        self.assertRedirects(resposta, reverse("els_meus_projectes"))
        clon = Projecte.objects.get(nom="Projecte sense hores")
        self.assertEqual(
            list(clon.specs.order_by("ordre").values_list("hores_estimades", flat=True)),
            [0, 0],
        )

    def test_clona_projecte_conserva_les_hores_si_no_es_demana_reset(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        resposta = self.client.post(
            reverse("clona_projecte", args=[self.projecte.id]),
            {"nom": "Projecte amb hores", "reseteja_hores_estimades": ""},
        )
        self.assertRedirects(resposta, reverse("els_meus_projectes"))
        clon = Projecte.objects.get(nom="Projecte amb hores")
        self.assertEqual(clon.specs.get().hores_estimades, 8)

    def test_clona_projecte_rebutja_un_nom_ocupat(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        resposta = self.client.post(
            reverse("clona_projecte", args=[self.projecte.id]),
            {"nom": "  projecte DE PROVA  "},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(resposta.json()["ok"])
        self.assertIn(
            "Ja existeix un projecte amb aquest nom.",
            resposta.json()["errors"],
        )
        self.assertEqual(Projecte.objects.count(), 1)

    def test_clona_projecte_rebutja_un_nom_buit(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        resposta = self.client.post(
            reverse("clona_projecte", args=[self.projecte.id]),
            {"nom": "   "},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn(
            "El nom del projecte és obligatori.",
            resposta.json()["errors"],
        )
        self.assertEqual(Projecte.objects.count(), 1)

    def test_clona_projecte_retorna_json_per_a_ajax(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        resposta = self.client.post(
            reverse("clona_projecte", args=[self.projecte.id]),
            {"nom": "Projecte clonat per Ajax"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resposta.status_code, 200)
        dades = resposta.json()
        self.assertTrue(dades["ok"])
        self.assertEqual(dades["redirect"], reverse("els_meus_projectes"))
        self.assertTrue(
            Projecte.objects.filter(nom="Projecte clonat per Ajax").exists()
        )

    def test_detall_projecte(self):
        response = self.client.get(reverse("projecte", args=[self.projecte.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pantalla d&#x27;inici")
        self.assertContains(response, "Sprint 1")
        self.assertNotContains(response, "Resta del backlog")

    def test_detall_projecte_mostra_la_resta_del_backlog(self):
        Spec.objects.create(
            nom="Spec sense sprint",
            projecte=self.projecte,
            ordre=2,
            hores_estimades=3,
        )
        response = self.client.get(reverse("projecte", args=[self.projecte.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resta del backlog")

        contingut = response.content.decode()
        index_sprint = contingut.index(
            'id="sprint-{}"'.format(self.sprint.id)
        )
        index_backlog = contingut.index('id="backlog"')
        index_spec = contingut.index("Spec sense sprint")
        self.assertLess(index_sprint, index_backlog)
        self.assertLess(index_backlog, index_spec)
        self.assertEqual(contingut.count("Pantalla d&#x27;inici"), 1)

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

    def test_qualifica_projecte_requereix_login(self):
        response = self.client.get(
            reverse("qualifica_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 302)

    def test_qualifica_projecte_fixat(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("qualifica_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Qualifica: Projecte de prova")
        self.assertContains(response, "Descarrega ODS")
        self.assertContains(
            response, reverse("els_meus_projectes")
        )
        self.assertNotContains(response, 'name="projecte_id"')

    def test_qualifica_projecte_nomes_per_administradors(self):
        User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="altre@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("qualifica_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_dialeg_qualificacio_mostra_mps_en_xips_sencers(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("qualifica_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "crea_xips_mps")
        self.assertContains(response, "etiqueta_mp")
        self.assertContains(response, 'xip.className = "chip"')
        self.assertContains(response, "xip.textContent = etiqueta_mp(mp)")
        self.assertContains(response, 'input.type = "number"')
        self.assertContains(response, "set_percentatge_done_spec")
        self.assertNotContains(response, "toggle_done_spec")
        self.assertNotContains(response, "substring(0, 4)")

    def test_tanca_dialeg_qualificacio_actualitza_la_vista(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("qualifica_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "modal.options.onCloseEnd = recarrega_vista")
        self.assertContains(response, "function recarrega_vista")
        self.assertContains(response, "desamentsPendents")
        self.assertContains(response, "window.location.reload()")

    def test_targetes_qualificacio_mostren_percentatges_per_mp(self):
        equip = Equip.objects.create(nom="Equip Alpha", projecte=self.projecte)
        quali = Qualificacio.objects.create(equip=equip, sprint=self.sprint)
        done_spec = DoneSpec.objects.create(
            qualificacio=quali, spec=self.spec, percentatge=100
        )
        self.assertEqual(done_spec.percentatge, 100)
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

    def test_algorismes_qualificacio_amb_percentatge_parcial(self):
        equip = Equip.objects.create(nom="Equip Alpha", projecte=self.projecte)
        quali = Qualificacio.objects.create(equip=equip, sprint=self.sprint)
        DoneSpec.objects.create(
            qualificacio=quali, spec=self.spec, percentatge=50
        )
        spec2 = Spec.objects.create(
            nom="Tancament de sessió",
            projecte=self.projecte,
            ordre=2,
            hores_estimades=2,
        )
        spec2.mp.add(self.mp)
        spec2.sprints.add(self.sprint)
        DoneSpec.objects.create(
            qualificacio=quali, spec=spec2, percentatge=0
        )

        self.assertEqual(quali.specs_completades(), "0.5 (25.0%)")
        self.assertEqual(quali.hores_completades(), "4.0 (40.0%)")
        dades = {d["nom"]: d for d in quali.percentatges_mps()}
        self.assertEqual(dades[self.mp.nom]["total"], 10.0)
        self.assertEqual(dades[self.mp.nom]["done"], 4.0)
        self.assertEqual(dades[self.mp.nom]["specs_total"], 2)
        self.assertEqual(dades[self.mp.nom]["specs_done"], 0.5)
        self.assertEqual(dades[self.mp.nom]["percentatge"], 40.0)
        self.assertEqual(
            quali.specs_completades_mps(),
            "{} : 0.5/2 (25.0%)<br>".format(self.mp.nom),
        )
        self.assertEqual(
            quali.specs_completades_mps_ponderat(),
            "{} : 40.0%<br>".format(self.mp.nom),
        )

    def test_api_actualitza_percentatge_done_spec(self):
        equip = Equip.objects.create(nom="Equip Alpha", projecte=self.projecte)
        quali = Qualificacio.objects.create(equip=equip, sprint=self.sprint)
        done_spec = DoneSpec.objects.create(
            qualificacio=quali, spec=self.spec, percentatge=0
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")

        response = self.client.post(
            reverse("set_percentatge_done_spec", args=[done_spec.id]),
            {"percentatge": "65.5"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["done_spec"]["percentatge"], 65.5)
        done_spec.refresh_from_db()
        self.assertEqual(done_spec.percentatge, 65.5)

        response = self.client.get(
            reverse("get_qualificacio", args=[quali.id])
        )
        self.assertEqual(
            response.json()["qualificacio"]["done_specs"][0]["percentatge"],
            65.5,
        )

        response = self.client.post(
            reverse("set_percentatge_done_spec", args=[done_spec.id]),
            {"percentatge": "101"},
        )
        self.assertEqual(response.status_code, 400)
        done_spec.refresh_from_db()
        self.assertEqual(done_spec.percentatge, 65.5)

    def test_api_actualitza_percentatges_mp_individuals(self):
        equip = Equip.objects.create(nom="Equip Alpha", projecte=self.projecte)
        quali = Qualificacio.objects.create(equip=equip, sprint=self.sprint)
        done_spec = DoneSpec.objects.create(
            qualificacio=quali, spec=self.spec, percentatge=0
        )
        mp2 = ModulProfessional.objects.create(
            numero=7, nom="Desenvolupament web en entorn servidor", cicle=self.cicle
        )
        self.spec.mp.add(mp2)
        self.client.login(username="profe@example.cat", password="contrasenya123")

        response = self.client.post(
            reverse("set_percentatges_done_spec_mp", args=[done_spec.id]),
            {
                "mp_{}".format(self.mp.id): "100",
                "mp_{}".format(mp2.id): "50",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["done_spec"]
        self.assertTrue(data["qualificacio_individual"])
        self.assertEqual(data["percentatge"], 75.0)
        self.assertEqual(
            {dada["id"]: dada["percentatge"] for dada in data["percentatges_mp"]},
            {self.mp.id: 100.0, mp2.id: 50.0},
        )
        self.assertEqual(
            {
                dada["id"]: dada["numero"]
                for dada in data["percentatges_mp"]
            },
            {self.mp.id: self.mp.numero, mp2.id: mp2.numero},
        )
        self.assertEqual(
            {
                dada["id"]: dada["numero"]
                for dada in data["spec"]["mp"]
            },
            {self.mp.id: self.mp.numero, mp2.id: mp2.numero},
        )

        done_spec.refresh_from_db()
        self.assertTrue(done_spec.qualificacio_individual)
        self.assertEqual(done_spec.percentatge, 75.0)
        self.assertEqual(
            {
                percentatge.mp_id: percentatge.percentatge
                for percentatge in DoneSpecPercentatgeMP.objects.filter(
                    done_spec=done_spec
                )
            },
            {self.mp.id: 100.0, mp2.id: 50.0},
        )

        dades = {d["obj"].id: d for d in quali.percentatges_mps()}
        self.assertEqual(dades[self.mp.id]["percentatge"], 100.0)
        self.assertEqual(dades[mp2.id]["percentatge"], 50.0)

    def test_percentatge_global_esborra_la_qualificacio_individual(self):
        equip = Equip.objects.create(nom="Equip Alpha", projecte=self.projecte)
        quali = Qualificacio.objects.create(equip=equip, sprint=self.sprint)
        done_spec = DoneSpec.objects.create(
            qualificacio=quali,
            spec=self.spec,
            percentatge=75,
            qualificacio_individual=True,
        )
        DoneSpecPercentatgeMP.objects.create(
            done_spec=done_spec, mp=self.mp, percentatge=75
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")

        response = self.client.post(
            reverse("set_percentatge_done_spec", args=[done_spec.id]),
            {"percentatge": "40"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["done_spec"]
        self.assertFalse(data["qualificacio_individual"])
        self.assertEqual(data["percentatge"], 40.0)
        self.assertEqual(
            data["percentatges_mp"][0]["percentatge"], 40.0
        )

        done_spec.refresh_from_db()
        self.assertFalse(done_spec.qualificacio_individual)
        self.assertEqual(done_spec.percentatge, 40.0)
        self.assertFalse(
            DoneSpecPercentatgeMP.objects.filter(done_spec=done_spec).exists()
        )

    def test_api_actualitza_percentatges_mp_valida_les_dades(self):
        equip = Equip.objects.create(nom="Equip Alpha", projecte=self.projecte)
        quali = Qualificacio.objects.create(equip=equip, sprint=self.sprint)
        done_spec = DoneSpec.objects.create(
            qualificacio=quali, spec=self.spec, percentatge=0
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")

        response = self.client.post(
            reverse("set_percentatges_done_spec_mp", args=[done_spec.id]),
            {"mp_{}".format(self.mp.id): "-1"},
        )
        self.assertEqual(response.status_code, 400)
        done_spec.refresh_from_db()
        self.assertFalse(done_spec.qualificacio_individual)
        self.assertFalse(
            DoneSpecPercentatgeMP.objects.filter(done_spec=done_spec).exists()
        )

    def test_dialeg_qualificacio_mostra_qualificacio_individual_per_mp(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("qualifica_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Qualificar per mòduls professionals")
        self.assertContains(response, "set_percentatges_done_spec_mp")
        self.assertContains(response, "spec-percentatges-mp")
        self.assertContains(response, "spec-percentatge-mp-input")
        self.assertContains(response, "qualificacio_individual")
        self.assertContains(response, "etiqueta_mp")

        equip = Equip.objects.create(nom="Equip Alpha", projecte=self.projecte)
        quali = Qualificacio.objects.create(equip=equip, sprint=self.sprint)
        DoneSpec.objects.create(qualificacio=quali, spec=self.spec, percentatge=100)
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
            qualificacio=quali1, spec=self.spec, percentatge=100
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
            qualificacio=quali2, spec=spec2, percentatge=0
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
            qualificacio=quali1, spec=spec3, percentatge=100
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

    def test_crea_equip_requereix_login(self):
        response = self.client.get(reverse("crea_equip"))
        self.assertEqual(response.status_code, 302)

    def test_crea_equip_amb_membres(self):
        self.user.centre = self.centre
        self.user.save(update_fields=["centre"])
        alumne = User.objects.create_user(
            username="alumne",
            email="alumne@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_equip"),
            {
                "nom": "Equip Nou",
                "descripcio": "Descripció de l'equip",
                "projecte": self.projecte.id,
                "membres": [self.user.id, alumne.id],
            },
        )
        self.assertRedirects(response, reverse("crea_equip"))
        equip = Equip.objects.get(nom="Equip Nou")
        self.assertEqual(equip.projecte, self.projecte)
        self.assertEqual(equip.descripcio, "Descripció de l'equip")
        self.assertEqual(set(equip.membres.all()), {self.user, alumne})

    def test_equip_detecta_els_identificadors_de_video_de_youtube(self):
        equip = Equip(nom="Equip vídeo", projecte=self.projecte)
        identificador = "dQw4w9WgXcQ"
        enllacos = (
            "https://www.youtube.com/watch?v={}".format(identificador),
            "https://youtu.be/{}?t=10".format(identificador),
            "https://youtube.com/shorts/{}".format(identificador),
            "https://www.youtube.com/embed/{}".format(identificador),
            "youtube.com/watch?v={}".format(identificador),
        )
        for enllac in enllacos:
            equip.link_video = enllac
            self.assertEqual(equip.video_youtube_id(), identificador)
            self.assertTrue(equip.es_video_youtube())

    def test_equip_amb_video_extern_mostra_el_domini(self):
        equip = Equip(
            nom="Equip extern",
            projecte=self.projecte,
            link_video="https://drive.google.com/file/d/abc/view",
        )
        self.assertEqual(equip.video_youtube_id(), "")
        self.assertFalse(equip.es_video_youtube())
        self.assertEqual(equip.domini_video(), "drive.google.com")

    def test_crea_equip_amb_enllac_de_video(self):
        self.user.centre = self.centre
        self.user.save(update_fields=["centre"])
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_equip"),
            {
                "nom": "Equip amb vídeo",
                "projecte": self.projecte.id,
                "link_video": "youtu.be/dQw4w9WgXcQ",
            },
        )
        self.assertRedirects(response, reverse("crea_equip"))
        equip = Equip.objects.get(nom="Equip amb vídeo")
        self.assertEqual(equip.link_video, "https://youtu.be/dQw4w9WgXcQ")

    def test_crea_equip_rebutja_un_enllac_de_video_invalid(self):
        self.user.centre = self.centre
        self.user.save(update_fields=["centre"])
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_equip"),
            {
                "nom": "Equip amb vídeo invàlid",
                "projecte": self.projecte.id,
                "link_video": "això no és una url",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "del vídeo no és una URL vàlida.")
        self.assertFalse(
            Equip.objects.filter(nom="Equip amb vídeo invàlid").exists()
        )

    def test_videos_mostra_preview_de_youtube_i_enllacos_externs(self):
        Equip.objects.create(
            nom="Equip YouTube",
            projecte=self.projecte,
            link_video="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        Equip.objects.create(
            nom="Equip Drive",
            projecte=self.projecte,
            link_video="https://drive.google.com/file/d/abc/view",
        )
        Equip.objects.create(nom="Equip sense vídeo", projecte=self.projecte)

        response = self.client.get(reverse("videos"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vídeos dels projectes Scrum")
        self.assertContains(response, "Equip YouTube")
        self.assertContains(response, "Equip Drive")
        self.assertNotContains(response, "Equip sense vídeo")
        self.assertContains(
            response,
            "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        )
        self.assertContains(response, "Aquest vídeo no és de YouTube.")
        self.assertContains(response, "drive.google.com")
        self.assertContains(
            response,
            reverse("projecte", args=[self.projecte.id]),
        )

    def test_navbar_mostra_enllac_a_videos(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("videos"))
        self.assertContains(response, "Vídeos")

    def test_crea_equip_afegeix_el_creador_com_a_membre(self):
        self.user.centre = self.centre
        self.user.save(update_fields=["centre"])
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_equip"),
            {"nom": "Equip del creador", "projecte": self.projecte.id},
        )
        self.assertRedirects(response, reverse("crea_equip"))
        equip = Equip.objects.get(nom="Equip del creador")
        self.assertIn(self.user, equip.membres.all())

    def test_crea_equip_no_permet_projectes_d_un_altre_centre(self):
        altre_centre = Centre.objects.create(
            nom="Institut Altre",
            poblacio="Tarragona",
            cp="43001",
            email="altre@example.cat",
        )
        altre_projecte = Projecte.objects.create(
            nom="Projecte aliè",
            centre=altre_centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        self.user.centre = self.centre
        self.user.save(update_fields=["centre"])
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_equip"),
            {"nom": "Equip intrus", "projecte": altre_projecte.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Equip.objects.filter(nom="Equip intrus").exists())

    def test_crea_equip_mostra_els_projectes_del_centre(self):
        altre_centre = Centre.objects.create(
            nom="Institut Altre",
            poblacio="Tarragona",
            cp="43001",
            email="altre@example.cat",
        )
        projecte_del_centre = Projecte.objects.create(
            nom="Projecte del centre",
            centre=self.centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        projecte_altre_centre = Projecte.objects.create(
            nom="Projecte d'un altre centre",
            centre=altre_centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        projecte_sense_centre = Projecte.objects.create(
            nom="Projecte sense centre",
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        self.user.centre = self.centre
        self.user.save(update_fields=["centre"])
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("crea_equip"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.projecte.nom)
        self.assertContains(response, projecte_del_centre.nom)
        self.assertNotContains(response, projecte_altre_centre.nom)
        self.assertNotContains(response, projecte_sense_centre.nom)

    def test_crea_equip_sense_centre_mostra_projectes_sense_centre(self):
        projecte_sense_centre = Projecte.objects.create(
            nom="Projecte sense centre",
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("crea_equip"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, projecte_sense_centre.nom)
        self.assertNotContains(response, self.projecte.nom)

    def test_els_meus_equips_requereix_login(self):
        response = self.client.get(reverse("els_meus_equips"))
        self.assertEqual(response.status_code, 302)

    def test_els_meus_equips_mostra_nomes_els_equips_propis(self):
        equip_propi = Equip.objects.create(nom="Equip Propi", projecte=self.projecte)
        equip_propi.membres.add(self.user)
        altre_usuari = User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        equip_altre = Equip.objects.create(nom="Equip Altre", projecte=self.projecte)
        equip_altre.membres.add(altre_usuari)
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("els_meus_equips"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Equip Propi")
        self.assertNotContains(response, "Equip Altre")

    def test_els_meus_equips_te_boto_per_crear_un_equip(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("els_meus_equips"))
        self.assertContains(response, reverse("crea_equip"))
        self.assertContains(response, "Crea equip")

    def test_els_meus_equips_mostra_botons_de_projecte_i_edicio(self):
        equip = Equip.objects.create(nom="Equip amb botons", projecte=self.projecte)
        equip.membres.add(self.user)
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("els_meus_equips"))
        self.assertContains(response, reverse("projecte", args=[self.projecte.id]))
        self.assertContains(response, reverse("edita_equip", args=[equip.id]))
        self.assertContains(response, "Anar al projecte")
        self.assertContains(response, "Editar equip")
        self.assertNotContains(
            response,
            '<a href="{}">{}</a>'.format(
                reverse("projecte", args=[self.projecte.id]), equip.nom
            ),
        )

    def test_edita_equip_requereix_login(self):
        equip = Equip.objects.create(nom="Equip privat", projecte=self.projecte)
        equip.membres.add(self.user)
        response = self.client.get(
            reverse("edita_equip", args=[equip.id])
        )
        self.assertEqual(response.status_code, 302)

    def test_edita_equip_mostra_les_dades_i_els_membres(self):
        equip = Equip.objects.create(
            nom="Equip editable",
            descripcio="Descripció original",
            link_video="https://youtu.be/dQw4w9WgXcQ",
            projecte=self.projecte,
        )
        equip.membres.add(self.user)
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("edita_equip", args=[equip.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edita l'equip")
        self.assertContains(response, 'value="Equip editable"')
        self.assertContains(response, "Descripció original")
        self.assertContains(response, 'value="https://youtu.be/dQw4w9WgXcQ"')
        self.assertContains(response, self.user.email)
        self.assertContains(response, "Desa els canvis")

    def test_edita_equip_actualitza_les_dades_i_els_membres(self):
        self.user.centre = self.centre
        self.user.save(update_fields=["centre"])
        alumne = User.objects.create_user(
            username="alumne-edicio",
            email="alumne-edicio@example.cat",
            password="contrasenya123",
        )
        equip = Equip.objects.create(
            nom="Equip original",
            descripcio="Descripció original",
            projecte=self.projecte,
        )
        equip.membres.add(self.user, alumne)
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("edita_equip", args=[equip.id]),
            {
                "nom": "Equip actualitzat",
                "descripcio": "Descripció nova",
                "link_video": "youtu.be/dQw4w9WgXcQ",
                "projecte": self.projecte.id,
                "membres": [self.user.id],
            },
        )
        self.assertRedirects(response, reverse("els_meus_equips"))
        equip.refresh_from_db()
        self.assertEqual(equip.nom, "Equip actualitzat")
        self.assertEqual(equip.descripcio, "Descripció nova")
        self.assertEqual(equip.link_video, "https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(equip.projecte, self.projecte)
        self.assertEqual(set(equip.membres.all()), {self.user})

    def test_edita_equip_permet_mantenir_el_mateix_nom(self):
        equip = Equip.objects.create(
            nom="Equip sense canvis de nom",
            descripcio="Descripció original",
            projecte=self.projecte,
        )
        equip.membres.add(self.user)
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("edita_equip", args=[equip.id]),
            {
                "nom": equip.nom,
                "descripcio": "Descripció actualitzada",
                "projecte": self.projecte.id,
                "membres": [self.user.id],
            },
        )
        self.assertRedirects(response, reverse("els_meus_equips"))
        equip.refresh_from_db()
        self.assertEqual(equip.descripcio, "Descripció actualitzada")

    def test_edita_equip_rebutja_un_nom_duplicat(self):
        Equip.objects.create(nom="Equip duplicat", projecte=self.projecte)
        equip = Equip.objects.create(nom="Equip propi", projecte=self.projecte)
        equip.membres.add(self.user)
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("edita_equip", args=[equip.id]),
            {
                "nom": "Equip duplicat",
                "projecte": self.projecte.id,
                "membres": [self.user.id],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Ja existeix un equip amb aquest nom en aquest projecte."
        )
        equip.refresh_from_db()
        self.assertEqual(equip.nom, "Equip propi")

    def test_edita_equip_rebutja_un_enllac_de_video_invalid(self):
        equip = Equip.objects.create(nom="Equip vídeo", projecte=self.projecte)
        equip.membres.add(self.user)
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("edita_equip", args=[equip.id]),
            {
                "nom": "Equip vídeo",
                "projecte": self.projecte.id,
                "link_video": "això no és una url",
                "membres": [self.user.id],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "del vídeo no és una URL vàlida.")
        equip.refresh_from_db()
        self.assertEqual(equip.link_video, "")

    def test_edita_equip_no_permet_editar_equips_d_altres(self):
        altre_usuari = User.objects.create_user(
            username="altre-membre",
            email="altre-membre@example.cat",
            password="contrasenya123",
        )
        equip = Equip.objects.create(nom="Equip aliè", projecte=self.projecte)
        equip.membres.add(altre_usuari)
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("edita_equip", args=[equip.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_navbar_mostra_els_meus_equips(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("els_meus_equips"))
        self.assertContains(response, "Els meus equips")
        self.assertNotContains(response, "Nou equip")

    def test_els_meus_projectes_requereix_login(self):
        response = self.client.get(reverse("els_meus_projectes"))
        self.assertEqual(response.status_code, 302)

    def test_els_meus_projectes_mostra_nomes_els_administrats(self):
        altre_usuari = User.objects.create_user(
            username="altre-admin",
            email="altre-admin@example.cat",
            password="contrasenya123",
        )
        projecte_altre = Projecte.objects.create(
            nom="Projecte d'un altre",
            centre=self.centre,
            cicle=self.cicle,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        projecte_altre.admins.add(altre_usuari)
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("els_meus_projectes"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.projecte.nom)
        self.assertNotContains(response, projecte_altre.nom)

    def test_els_meus_projectes_te_boto_per_crear_un_projecte(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("els_meus_projectes"))
        self.assertContains(response, reverse("crea_projecte"))
        self.assertContains(response, "Nou projecte")

    def test_els_meus_projectes_mostra_les_accions_de_cada_projecte(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("els_meus_projectes"))
        self.assertNotContains(response, "Go!")
        self.assertContains(response, reverse("projecte", args=[self.projecte.id]))
        self.assertContains(
            response, reverse("edita_projecte", args=[self.projecte.id])
        )
        self.assertContains(
            response, reverse("elimina_projecte", args=[self.projecte.id])
        )
        self.assertContains(
            response, reverse("qualifica_projecte", args=[self.projecte.id])
        )
        self.assertContains(response, "Qualifica el projecte")
        self.assertContains(response, "Segur que vols eliminar aquest projecte?")

    def test_edita_projecte_requereix_login(self):
        response = self.client.get(
            reverse("edita_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 302)

    def test_edita_projecte_nomes_per_administradors(self):
        User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="altre@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("edita_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_edita_projecte_actualitza_les_dades(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("edita_projecte", args=[self.projecte.id])
        )
        self.assertContains(response, "Edita el projecte")
        self.assertContains(response, self.projecte.nom)
        self.assertContains(response, 'data-ajax-missatge="#ajax-missatge"')

        response = self.client.post(
            reverse("edita_projecte", args=[self.projecte.id]),
            {
                "nom": "Projecte actualitzat",
                "descripcio": "Nova descripció",
                "centre": str(self.centre.pk),
                "cicle": str(self.cicle.pk),
                "inici": "2026-03-01",
                "final": "2026-04-01",
            },
        )
        self.assertRedirects(response, reverse("els_meus_projectes"))
        self.projecte.refresh_from_db()
        self.assertEqual(self.projecte.nom, "Projecte actualitzat")
        self.assertEqual(self.projecte.descripcio, "Nova descripció")
        self.assertEqual(self.projecte.inici, datetime.date(2026, 3, 1))
        self.assertEqual(self.projecte.final, datetime.date(2026, 4, 1))

    def test_edita_projecte_mostra_la_seccio_de_sprints(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("edita_projecte", args=[self.projecte.id])
        )
        self.assertContains(response, "Sprints")
        self.assertContains(response, self.sprint.nom)
        self.assertContains(
            response, reverse("crea_sprint", args=[self.projecte.id])
        )
        self.assertContains(response, reverse("edita_sprint", args=[self.sprint.id]))
        self.assertContains(response, 'id="sprint-missatge-{}"'.format(self.sprint.id))
        self.assertContains(
            response,
            'data-ajax-missatge="#sprint-missatge-{}"'.format(self.sprint.id),
        )
        self.assertContains(response, 'id="sprint-missatge-nou"')
        self.assertNotContains(response, "sprint-nou-notes")
        self.assertNotContains(response, "sprint-notes-{}".format(self.sprint.id))

    def test_crea_sprint_requereix_login(self):
        response = self.client.post(
            reverse("crea_sprint", args=[self.projecte.id]),
            {"nom": "Sprint nou", "inici": "2026-01-01", "final": "2026-01-07"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Sprint.objects.filter(nom="Sprint nou").exists())

    def test_crea_sprint_nomes_per_administradors(self):
        User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="altre@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_sprint", args=[self.projecte.id]),
            {"nom": "Sprint nou", "inici": "2026-01-01", "final": "2026-01-07"},
        )
        self.assertEqual(response.status_code, 404)

    def test_crea_sprint_amb_post(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_sprint", args=[self.projecte.id]),
            {
                "nom": "Sprint nou",
                "inici": "2026-01-01",
                "final": "2026-01-07",
            },
        )
        self.assertRedirects(
            response, reverse("edita_projecte", args=[self.projecte.id])
        )
        sprint = Sprint.objects.get(nom="Sprint nou")
        self.assertEqual(sprint.projecte, self.projecte)
        self.assertEqual(sprint.inici, datetime.date(2026, 1, 1))
        self.assertEqual(sprint.final, datetime.date(2026, 1, 7))

    def test_edita_sprint_requereix_login(self):
        response = self.client.post(
            reverse("edita_sprint", args=[self.sprint.id]),
            {"nom": "Canviat", "inici": "2026-01-01", "final": "2026-01-07"},
        )
        self.assertEqual(response.status_code, 302)
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.nom, "Sprint 1")

    def test_edita_sprint_nomes_per_administradors(self):
        User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="altre@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("edita_sprint", args=[self.sprint.id]),
            {"nom": "Canviat", "inici": "2026-01-01", "final": "2026-01-07"},
        )
        self.assertEqual(response.status_code, 404)

    def test_edita_sprint_amb_post(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("edita_sprint", args=[self.sprint.id]),
            {
                "nom": "Sprint actualitzat",
                "inici": "2026-02-01",
                "final": "2026-02-14",
            },
        )
        self.assertRedirects(
            response, reverse("edita_projecte", args=[self.projecte.id])
        )
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.nom, "Sprint actualitzat")
        self.assertEqual(self.sprint.inici, datetime.date(2026, 2, 1))
        self.assertEqual(self.sprint.final, datetime.date(2026, 2, 14))

    def test_edita_projecte_mostra_la_seccio_de_specs(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("edita_projecte", args=[self.projecte.id])
        )
        self.assertContains(response, "Nova spec")
        self.assertContains(response, self.spec.nom, html=True)
        self.assertContains(
            response, reverse("crea_spec", args=[self.projecte.id])
        )
        self.assertContains(response, 'class="spec-hores-input"')
        self.assertContains(
            response,
            reverse("actualitza_hores_spec", args=[self.spec.id]),
        )
        self.assertContains(response, 'data-original="8"')
        self.assertContains(response, 'id="spec-nou-nom"')
        self.assertContains(response, 'id="spec-missatge-nou"')
        self.assertContains(response, 'data-ajax-missatge="#spec-missatge-nou"')
        self.assertContains(response, 'id="spec-mp-cerca"')
        self.assertContains(response, 'id="spec-sprints-cerca"')
        self.assertContains(response, reverse("cerca_moduls"))
        self.assertContains(response, reverse("cerca_sprints"))
        self.assertContains(
            response,
            '<h3 id="projecte-nom">{}</h3>'.format(self.projecte.nom),
            html=True,
        )
        contingut = response.content.decode()
        self.assertLess(
            contingut.index("<h4>Sprints</h4>"),
            contingut.index("<h4>Specs</h4>"),
        )

    def test_edita_projecte_mostra_la_descripcio_de_les_specs_col_lapsada(self):
        spec = Spec.objects.create(
            nom="Spec amb descripció",
            projecte=self.projecte,
            ordre=2,
            descripcio="<p>Text desplegable</p>",
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("edita_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="spec-descripcio"')
        self.assertContains(response, 'colspan="5"')
        self.assertContains(response, 'spec-fila-senar')
        self.assertContains(response, 'spec-descripcio-fila spec-fila-')
        self.assertContains(response, "Text desplegable")
        self.assertContains(
            response, 'data-spec-id="{}"'.format(spec.id)
        )
        self.assertContains(response, 'draggable="true"')
        self.assertContains(response, 'class="spec-drag-handle"')
        self.assertContains(
            response, 'data-spec-descripcio="{}"'.format(spec.id)
        )
        self.assertContains(
            response, reverse("reordena_specs", args=[self.projecte.id])
        )
        self.assertContains(response, 'id="specs-missatge"')
        self.assertContains(response, "<th>Accions</th>")
        self.assertContains(
            response,
            'data-actualitza-url="{}"'.format(
                reverse("actualitza_spec", args=[spec.id])
            ),
        )
        self.assertContains(
            response,
            'class="btn-small waves-effect waves-light blue spec-edita"',
        )
        self.assertContains(response, 'data-spec-nom="Spec amb descripció"')
        self.assertContains(
            response, 'data-spec-descripcio-html="&lt;p&gt;Text desplegable&lt;/p&gt;"'
        )
        self.assertContains(response, 'id="spec-edicio-form"')
        self.assertContains(response, "data-ajax-spec-edit")
        self.assertContains(response, 'id="spec-edit-nom"')
        self.assertContains(response, 'id="spec-edit-mp-cerca"')
        self.assertContains(response, 'id="spec-edit-sprints-cerca"')
        self.assertNotContains(response, "<th>Descripció</th>")
        self.assertNotContains(
            response, '<details class="spec-descripcio" open>'
        )

    def test_reordena_specs_amb_ajax(self):
        segona = Spec.objects.create(
            nom="Segona spec",
            projecte=self.projecte,
            ordre=2,
        )
        tercera = Spec.objects.create(
            nom="Tercera spec",
            projecte=self.projecte,
            ordre=3,
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("reordena_specs", args=[self.projecte.id]),
            {
                "ids": [
                    str(tercera.id),
                    str(self.spec.id),
                    str(segona.id),
                ]
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["ordre_nova_spec"], 4)
        self.assertLess(
            data["html"].index("Tercera spec"),
            data["html"].index("Segona spec"),
        )

        noms = list(
            Spec.objects.filter(projecte=self.projecte)
            .order_by("ordre", "id")
            .values_list("nom", flat=True)
        )
        self.assertEqual(noms, ["Tercera spec", "Pantalla d'inici", "Segona spec"])
        self.assertEqual(Spec.objects.get(pk=tercera.pk).ordre, 1)
        self.assertEqual(Spec.objects.get(pk=segona.pk).ordre, 3)

    def test_reordena_specs_requereix_totes_les_specs(self):
        Spec.objects.create(
            nom="Segona spec",
            projecte=self.projecte,
            ordre=2,
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("reordena_specs", args=[self.projecte.id]),
            {"ids": [str(self.spec.id)]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.spec.refresh_from_db()
        self.assertEqual(self.spec.ordre, 1)

    def test_reordena_specs_nomes_per_administradors(self):
        User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="altre@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("reordena_specs", args=[self.projecte.id]),
            {"ids": [str(self.spec.id)]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 404)
        self.spec.refresh_from_db()
        self.assertEqual(self.spec.ordre, 1)

    def test_actualitza_spec_amb_ajax(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("actualitza_spec", args=[self.spec.id]),
            {
                "nom": "Spec editada",
                "descripcio": "<p>Descripció editada</p>",
                "ordre": "5",
                "hores_estimades": "3.5",
                "mp": [str(self.mp.id)],
                "sprints": [str(self.sprint.id)],
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(
            data["missatge"], "Spec «Spec editada» actualitzada correctament."
        )
        self.assertIn("Spec editada", data["html"])
        self.assertEqual(data["ordre_nova_spec"], 6)

        self.spec.refresh_from_db()
        self.assertEqual(self.spec.nom, "Spec editada")
        self.assertEqual(self.spec.descripcio, "<p>Descripció editada</p>")
        self.assertEqual(self.spec.ordre, 5)
        self.assertEqual(self.spec.hores_estimades, 3.5)
        self.assertIn(self.mp, self.spec.mp.all())
        self.assertIn(self.sprint, self.spec.sprints.all())

    def test_actualitza_spec_pot_treure_mp_i_sprints(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("actualitza_spec", args=[self.spec.id]),
            {
                "nom": self.spec.nom,
                "descripcio": self.spec.descripcio,
                "ordre": str(self.spec.ordre),
                "hores_estimades": str(self.spec.hores_estimades),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertFalse(self.spec.mp.exists())
        self.assertFalse(self.spec.sprints.exists())

    def test_actualitza_spec_valida_les_dades(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("actualitza_spec", args=[self.spec.id]),
            {"nom": "", "ordre": "-1", "hores_estimades": "-2"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("El nom de la spec és obligatori.", data["errors"])
        self.spec.refresh_from_db()
        self.assertEqual(self.spec.nom, "Pantalla d'inici")
        self.assertEqual(self.spec.ordre, 1)

    def test_actualitza_spec_nomes_per_administradors(self):
        User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="altre@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("actualitza_spec", args=[self.spec.id]),
            {
                "nom": "Spec editada",
                "ordre": "1",
                "hores_estimades": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 404)

    def test_actualitza_spec_requereix_login(self):
        response = self.client.post(
            reverse("actualitza_spec", args=[self.spec.id]),
            {
                "nom": "Spec editada",
                "ordre": "1",
                "hores_estimades": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 302)

    def test_actualitza_spec_requereix_post(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("actualitza_spec", args=[self.spec.id])
        )
        self.assertEqual(response.status_code, 405)

    def test_actualitza_hores_spec_amb_ajax(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("actualitza_hores_spec", args=[self.spec.id]),
            {"hores_estimades": "5.5"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["hores_estimades"], 5.5)
        self.spec.refresh_from_db()
        self.assertEqual(self.spec.hores_estimades, 5.5)

    def test_actualitza_hores_spec_valida_les_dades(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        for hores in ("-2", "no-numèric"):
            response = self.client.post(
                reverse("actualitza_hores_spec", args=[self.spec.id]),
                {"hores_estimades": hores},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.json()["ok"])
        self.spec.refresh_from_db()
        self.assertEqual(self.spec.hores_estimades, 8)

    def test_actualitza_hores_spec_nomes_per_administradors(self):
        User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="altre@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("actualitza_hores_spec", args=[self.spec.id]),
            {"hores_estimades": "3"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 404)

    def test_actualitza_hores_spec_requereix_login(self):
        response = self.client.post(
            reverse("actualitza_hores_spec", args=[self.spec.id]),
            {"hores_estimades": "3"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 302)

    def test_actualitza_hores_spec_requereix_post(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("actualitza_hores_spec", args=[self.spec.id])
        )
        self.assertEqual(response.status_code, 405)

    def test_crea_spec_requereix_login(self):
        response = self.client.post(
            reverse("crea_spec", args=[self.projecte.id]),
            {"nom": "Spec nova", "ordre": "2", "hores_estimades": "4"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Spec.objects.filter(nom="Spec nova").exists())

    def test_crea_spec_nomes_per_administradors(self):
        User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="altre@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_spec", args=[self.projecte.id]),
            {"nom": "Spec nova", "ordre": "2", "hores_estimades": "4"},
        )
        self.assertEqual(response.status_code, 404)

    def test_crea_spec_amb_post(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_spec", args=[self.projecte.id]),
            {
                "nom": "Spec nova",
                "descripcio": "Descripció de la spec",
                "ordre": "2",
                "hores_estimades": "4.5",
                "mp": [str(self.mp.id)],
                "sprints": [str(self.sprint.id)],
            },
        )
        self.assertRedirects(
            response, reverse("edita_projecte", args=[self.projecte.id])
        )
        spec = Spec.objects.get(nom="Spec nova")
        self.assertEqual(spec.projecte, self.projecte)
        self.assertEqual(spec.descripcio, "Descripció de la spec")
        self.assertEqual(spec.ordre, 2)
        self.assertEqual(spec.hores_estimades, 4.5)
        self.assertIn(self.mp, spec.mp.all())
        self.assertIn(self.sprint, spec.sprints.all())

    def test_crea_spec_valida_les_dades(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_spec", args=[self.projecte.id]),
            {"nom": "", "ordre": "-1", "hores_estimades": "-2"},
        )
        self.assertRedirects(
            response, reverse("edita_projecte", args=[self.projecte.id])
        )
        self.assertFalse(Spec.objects.filter(projecte=self.projecte, nom="").exists())

    def test_edita_projecte_amb_ajax(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("edita_projecte", args=[self.projecte.id]),
            {
                "nom": "Projecte AJAX",
                "descripcio": "<p>Descripció AJAX</p>",
                "centre": str(self.centre.pk),
                "cicle": str(self.cicle.pk),
                "inici": "2026-03-01",
                "final": "2026-04-01",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["nom"], "Projecte AJAX")
        self.assertEqual(data["descripcio"], "<p>Descripció AJAX</p>")
        self.assertNotIn("redirect", data)
        self.projecte.refresh_from_db()
        self.assertEqual(self.projecte.nom, "Projecte AJAX")

    def test_edita_projecte_amb_ajax_retorna_errors(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("edita_projecte", args=[self.projecte.id]),
            {
                "nom": "",
                "descripcio": "",
                "centre": str(self.centre.pk),
                "cicle": str(self.cicle.pk),
                "inici": "2026-03-01",
                "final": "2026-04-01",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertTrue(
            any("obligatori" in error for error in data["errors"])
        )

    def test_crea_sprint_amb_ajax(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_sprint", args=[self.projecte.id]),
            {
                "nom": "Sprint AJAX",
                "inici": "2026-01-01",
                "final": "2026-01-07",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("Sprint AJAX", data["html"])
        self.assertNotIn("redirect", data)
        self.assertTrue(
            Sprint.objects.filter(
                nom="Sprint AJAX", projecte=self.projecte
            ).exists()
        )

    def test_edita_sprint_amb_ajax(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("edita_sprint", args=[self.sprint.id]),
            {
                "nom": "Sprint AJAX actualitzat",
                "inici": "2026-02-01",
                "final": "2026-02-14",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("Sprint AJAX actualitzat", data["html"])
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.nom, "Sprint AJAX actualitzat")

    def test_crea_spec_amb_ajax(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_spec", args=[self.projecte.id]),
            {
                "nom": "Spec AJAX",
                "descripcio": "Descripció AJAX",
                "ordre": "2",
                "hores_estimades": "4.5",
                "mp": [str(self.mp.id)],
                "sprints": [str(self.sprint.id)],
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("Spec AJAX", data["html"])
        self.assertEqual(data["ordre_nova_spec"], 3)
        self.assertNotIn("redirect", data)
        spec = Spec.objects.get(nom="Spec AJAX")
        self.assertIn(self.mp, spec.mp.all())
        self.assertIn(self.sprint, spec.sprints.all())

    def test_crea_spec_amb_ajax_retorna_errors(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_spec", args=[self.projecte.id]),
            {"nom": "", "ordre": "-1", "hores_estimades": "-2"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(len(data["errors"]), 3)

    def test_elimina_projecte_requereix_login(self):
        response = self.client.post(
            reverse("elimina_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Projecte.objects.filter(pk=self.projecte.pk).exists())

    def test_elimina_projecte_nomes_per_administradors(self):
        User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="altre@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("elimina_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Projecte.objects.filter(pk=self.projecte.pk).exists())

    def test_elimina_projecte_amb_post(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("elimina_projecte", args=[self.projecte.id])
        )
        self.assertRedirects(response, reverse("els_meus_projectes"))
        self.assertTrue(Projecte.objects.filter(pk=self.projecte.pk).exists())

        response = self.client.post(
            reverse("elimina_projecte", args=[self.projecte.id])
        )
        self.assertRedirects(response, reverse("els_meus_projectes"))
        self.assertFalse(Projecte.objects.filter(pk=self.projecte.pk).exists())

    def test_crea_projecte_requereix_login(self):
        response = self.client.get(reverse("crea_projecte"))
        self.assertEqual(response.status_code, 302)

    def test_crea_projecte_mostra_l_autocompletat_de_centre(self):
        self.user.centre = self.centre
        self.user.save(update_fields=["centre"])
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("crea_projecte"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="centre-cerca"')
        self.assertContains(response, 'id="centre-resultats"')
        self.assertContains(response, reverse("cerca_centres"))
        self.assertContains(response, 'value="{}"'.format(self.centre))

    def test_crea_projecte_mostra_l_autocompletat_de_cicle(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("crea_projecte"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="cicle-cerca"')
        self.assertContains(response, 'id="cicle-resultats"')
        self.assertContains(response, reverse("cerca_cicles"))

    def test_formularis_de_descripcio_amb_editor_enriquit(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("crea_projecte"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="projecte_descripcio"')
        self.assertContains(response, "django_ckeditor_5")

        response = self.client.get(
            reverse("edita_projecte", args=[self.projecte.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="projecte_descripcio"')
        self.assertContains(response, 'id="spec_descripcio"')

    def test_crea_projecte_afegeix_el_creador_com_a_administrador(self):
        self.user.centre = self.centre
        self.user.save(update_fields=["centre"])
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_projecte"),
            {
                "nom": "Projecte Nou",
                "descripcio": "Descripció del projecte",
                "centre": str(self.centre.pk),
                "cicle": str(self.cicle.pk),
                "inici": "2026-01-10",
                "final": "2026-02-10",
            },
        )
        self.assertRedirects(response, reverse("els_meus_projectes"))
        projecte = Projecte.objects.get(nom="Projecte Nou")
        self.assertEqual(projecte.descripcio, "Descripció del projecte")
        self.assertEqual(projecte.centre, self.centre)
        self.assertEqual(projecte.cicle, self.cicle)
        self.assertEqual(projecte.inici, datetime.date(2026, 1, 10))
        self.assertEqual(projecte.final, datetime.date(2026, 2, 10))
        self.assertIn(self.user, projecte.admins.all())

    def test_crea_projecte_usa_el_centre_de_l_usuari_per_defecte(self):
        self.user.centre = self.centre
        self.user.save(update_fields=["centre"])
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_projecte"),
            {
                "nom": "Projecte sense centre",
                "inici": "2026-01-10",
                "final": "2026-02-10",
            },
        )
        self.assertRedirects(response, reverse("els_meus_projectes"))
        projecte = Projecte.objects.get(nom="Projecte sense centre")
        self.assertEqual(projecte.centre, self.centre)
        self.assertIsNone(projecte.cicle)

    def test_crea_projecte_valida_les_dades(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("crea_projecte"),
            {"nom": "", "inici": "", "final": "2026-01-10"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El nom del projecte és obligatori.")
        self.assertContains(response, "La data d&#x27;inici no és vàlida.")

        response = self.client.post(
            reverse("crea_projecte"),
            {
                "nom": "Dates incorrectes",
                "inici": "2026-02-10",
                "final": "2026-01-10",
            },
        )
        self.assertContains(
            response, "La data final ha de ser posterior a la data d&#x27;inici."
        )

    def test_navbar_mostra_els_meus_projectes(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("els_meus_projectes"))
        self.assertContains(response, "Els meus projectes")

    def test_cerca_usuaris_mostra_email_amb_una_unica_coincidencia(self):
        unica = User.objects.create_user(
            username="unica",
            email="unica@example.cat",
            password="contrasenya123",
        )
        User.objects.create_user(
            username="unica2",
            email="unica2@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("cerca_usuaris"), {"q": "unica@"})
        self.assertEqual(response.status_code, 200)
        resultats = response.json()["results"]
        self.assertEqual(len(resultats), 1)
        self.assertEqual(resultats[0]["email"], unica.email)

    def test_cerca_usuaris_amaga_emails_amb_mes_duna_coincidencia(self):
        User.objects.create_user(
            username="unica",
            email="unica@example.cat",
            password="contrasenya123",
        )
        User.objects.create_user(
            username="unica2",
            email="unica2@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("cerca_usuaris"), {"q": "example.cat"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_cerca_usuaris_requereix_login(self):
        response = self.client.get(reverse("cerca_usuaris"), {"q": "profe@"})
        self.assertEqual(response.status_code, 302)

    def test_perfil_requereix_login(self):
        response = self.client.get(reverse("perfil"))
        self.assertEqual(response.status_code, 302)

    def test_perfil_mostra_les_dades_de_l_usuari(self):
        self.user.first_name = "Anna"
        self.user.last_name = "Pérez"
        self.user.centre = self.centre
        self.user.save()
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("perfil"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Anna"')
        self.assertContains(response, 'value="Pérez"')
        self.assertContains(response, self.centre.nom)

    def test_perfil_actualitza_nom_cognom_i_centre(self):
        altre_centre = Centre.objects.create(
            nom="Institut Nou",
            poblacio="Girona",
            cp="17001",
            email="info@nou.cat",
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("perfil"),
            {
                "first_name": "Anna",
                "last_name": "Pérez",
                "centre": altre_centre.id,
            },
        )
        self.assertRedirects(response, reverse("perfil"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Anna")
        self.assertEqual(self.user.last_name, "Pérez")
        self.assertEqual(self.user.centre, altre_centre)

    def test_perfil_accepta_deixar_el_centre_buit(self):
        self.user.centre = self.centre
        self.user.save()
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("perfil"),
            {"first_name": "Anna", "last_name": "Pérez", "centre": ""},
        )
        self.assertRedirects(response, reverse("perfil"))
        self.user.refresh_from_db()
        self.assertIsNone(self.user.centre)

    def test_perfil_rebutja_un_centre_inexistent(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("perfil"),
            {"first_name": "Anna", "last_name": "Pérez", "centre": "999999"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tria un centre educatiu vàlid.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "")

    def test_perfil_crea_un_centre_nou(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("perfil"),
            {
                "first_name": "Anna",
                "last_name": "Pérez",
                "nou_centre_nom": "Institut Nou",
                "nou_centre_poblacio": "Girona",
                "nou_centre_cp": "17001",
                "nou_centre_email": "info@nou.cat",
            },
        )
        self.assertRedirects(response, reverse("perfil"))
        centre = Centre.objects.get(nom="Institut Nou")
        self.assertEqual(centre.poblacio, "Girona")
        self.assertEqual(centre.cp, "17001")
        self.assertEqual(centre.email, "info@nou.cat")
        self.user.refresh_from_db()
        self.assertEqual(self.user.centre, centre)

    def test_perfil_crea_un_centre_amb_tots_els_camps(self):
        cicle = Cicle.objects.create(
            grau="CFGS",
            codi="CFGS-001",
            nom="Desenvolupament d'Aplicacions Web",
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("perfil"),
            {
                "first_name": "Anna",
                "last_name": "Pérez",
                "nou_centre_nom": "Institut Complet",
                "nou_centre_direccio": "Carrer Major, 1",
                "nou_centre_poblacio": "Girona",
                "nou_centre_cp": "17001",
                "nou_centre_telefon": "972 20 20 20",
                "nou_centre_codi": "17001234",
                "nou_centre_email": "info@complet.cat",
                "nou_centre_web": "https://complet.cat",
                "nou_centre_descripcio": "Centre de prova",
                "nou_centre_imatge": "https://complet.cat/logo.png",
                "nou_centre_cicles": [str(cicle.pk)],
            },
        )
        self.assertRedirects(response, reverse("perfil"))
        centre = Centre.objects.get(nom="Institut Complet")
        self.assertEqual(centre.direccio, "Carrer Major, 1")
        self.assertEqual(centre.poblacio, "Girona")
        self.assertEqual(centre.cp, "17001")
        self.assertEqual(centre.telefon, "972 20 20 20")
        self.assertEqual(centre.codi, 17001234)
        self.assertEqual(centre.email, "info@complet.cat")
        self.assertEqual(centre.web, "https://complet.cat")
        self.assertEqual(centre.descripcio, "Centre de prova")
        self.assertEqual(centre.imatge, "https://complet.cat/logo.png")
        self.assertIn(cicle, centre.cicles.all())

    def test_perfil_valida_el_centre_nou(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("perfil"),
            {
                "first_name": "Anna",
                "last_name": "Pérez",
                "nou_centre_nom": "Institut Nou",
                "nou_centre_poblacio": "",
                "nou_centre_cp": "123",
                "nou_centre_email": "no-valid",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La població del centre és obligatòria.")
        self.assertContains(response, "El codi postal ha de tenir 5 dígits.")
        self.assertContains(response, "El correu del centre no és vàlid.")
        self.assertFalse(Centre.objects.filter(nom="Institut Nou").exists())

    def test_cerca_centres_filtra_per_nom_i_poblacio(self):
        Centre.objects.create(
            nom="Institut del Bosc",
            poblacio="Girona",
            cp="17001",
            email="bosc@example.cat",
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("cerca_centres"), {"q": "Girona"})
        self.assertEqual(response.status_code, 200)
        resultats = response.json()["results"]
        self.assertEqual(len(resultats), 1)
        self.assertEqual(resultats[0]["nom"], "Institut del Bosc")

    def test_cerca_centres_requereix_login(self):
        response = self.client.get(reverse("cerca_centres"), {"q": "Exemple"})
        self.assertEqual(response.status_code, 302)

    def test_cerca_cicles_filtra_per_nom_codi_i_grau(self):
        cicle = Cicle.objects.create(
            grau="CFGM",
            codi="CFGM-001",
            nom="Sistemes Microinformàtics i Xarxes",
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        for terme in ("Microinformàtics", "CFGM-001", "CFGM"):
            response = self.client.get(reverse("cerca_cicles"), {"q": terme})
            self.assertEqual(response.status_code, 200)
            resultats = response.json()["results"]
            self.assertEqual(len(resultats), 1)
            self.assertEqual(resultats[0]["id"], cicle.pk)

    def test_cerca_cicles_requereix_login(self):
        response = self.client.get(reverse("cerca_cicles"), {"q": "CFGS"})
        self.assertEqual(response.status_code, 302)

    def test_cerca_moduls_filtra_pel_projecte(self):
        altre_cicle = Cicle.objects.create(
            grau="CFGM", codi="SMX", nom="Sistemes Microinformàtics"
        )
        altre_mp = ModulProfessional.objects.create(
            numero=1, nom="Mòdul d'un altre cicle", cicle=altre_cicle
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("cerca_moduls"),
            {"q": "web", "projecte_id": self.projecte.id},
        )
        self.assertEqual(response.status_code, 200)
        ids = [resultat["id"] for resultat in response.json()["results"]]
        self.assertIn(self.mp.id, ids)
        self.assertNotIn(altre_mp.id, ids)

    def test_cerca_sprints_filtra_pel_projecte(self):
        altre_projecte = Projecte.objects.create(
            nom="Altre projecte",
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=30),
        )
        Sprint.objects.create(
            nom="Sprint d'un altre projecte",
            projecte=altre_projecte,
            inici=datetime.date.today(),
            final=datetime.date.today() + datetime.timedelta(days=7),
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(
            reverse("cerca_sprints"),
            {"q": "Sprint", "projecte_id": self.projecte.id},
        )
        self.assertEqual(response.status_code, 200)
        ids = [resultat["id"] for resultat in response.json()["results"]]
        self.assertEqual(ids, [self.sprint.id])

    def test_cerca_moduls_i_sprints_requereixen_login(self):
        for nom in ("cerca_moduls", "cerca_sprints"):
            response = self.client.get(
                reverse(nom), {"q": "Sprint", "projecte_id": self.projecte.id}
            )
            self.assertEqual(response.status_code, 302)

    def test_cerca_moduls_i_sprints_nomes_per_administradors(self):
        User.objects.create_user(
            username="altre",
            email="altre@example.cat",
            password="contrasenya123",
        )
        self.client.login(username="altre@example.cat", password="contrasenya123")
        for nom in ("cerca_moduls", "cerca_sprints"):
            response = self.client.get(
                reverse(nom), {"q": "Sprint", "projecte_id": self.projecte.id}
            )
            self.assertEqual(response.status_code, 404)

    def test_perfil_mante_els_cicles_seleccionats_si_hi_ha_errors(self):
        cicle = Cicle.objects.create(
            grau="CFGS",
            codi="CFGS-001",
            nom="Desenvolupament d'Aplicacions Web",
        )
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.post(
            reverse("perfil"),
            {
                "first_name": "Anna",
                "last_name": "Pérez",
                "nou_centre_nom": "Institut Complet",
                "nou_centre_poblacio": "",
                "nou_centre_cp": "17001",
                "nou_centre_email": "info@complet.cat",
                "nou_centre_cicles": [str(cicle.pk)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<input type="hidden" name="nou_centre_cicles" value="{}"'.format(cicle.pk),
            html=False,
        )

    def test_perfil_mostra_l_autocompletat_i_el_formulari_de_centre(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("perfil"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="centre-cerca"')
        self.assertContains(response, reverse("cerca_centres"))
        self.assertContains(response, 'name="nou_centre_nom"')
        self.assertContains(response, 'name="nou_centre_direccio"')
        self.assertContains(response, 'name="nou_centre_poblacio"')
        self.assertContains(response, 'name="nou_centre_cp"')
        self.assertContains(response, 'name="nou_centre_telefon"')
        self.assertContains(response, 'name="nou_centre_codi"')
        self.assertContains(response, 'name="nou_centre_email"')
        self.assertContains(response, 'name="nou_centre_web"')
        self.assertContains(response, 'name="nou_centre_descripcio"')
        self.assertContains(response, 'name="nou_centre_imatge"')
        self.assertNotContains(response, "nou_centre_admins")
        self.assertContains(response, 'id="cicle-cerca"')
        self.assertContains(response, 'id="cicle-resultats"')
        self.assertContains(response, reverse("cerca_cicles"))
        self.assertContains(response, "són obligatoris")
        self.assertContains(response, "Crea un nou centre educatiu")

    def test_perfil_carrega_amb_un_usuari_sense_nom_ni_centre(self):
        usuari = User.objects.create_user(
            username="sense-dades",
            email="sense-dades@example.cat",
            password="contrasenya123",
        )
        self.client.force_login(usuari)
        response = self.client.get(reverse("perfil"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value=""')

    def test_navbar_mostra_l_enllac_al_perfil(self):
        self.client.login(username="profe@example.cat", password="contrasenya123")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("perfil"))
