import datetime

from django.test import TestCase, override_settings
from django.urls import reverse

from . import insignies, kanban
from .models import (
    Cicle,
    DoneSpec,
    Equip,
    ModulProfessional,
    Projecte,
    Qualificacio,
    Spec,
    Sprint,
    TascaBloqueig,
    TascaEquip,
    TascaEvent,
    User,
)
from .views import _clona_projecte


def _usuari(nom, **extra):
    return User.objects.create_user(
        username=nom,
        email="{}@example.cat".format(nom),
        password="contrasenya123",
        first_name=nom.capitalize(),
        last_name="Prova",
        **extra,
    )


class BaseKanban(TestCase):
    def setUp(self):
        self.cicle = Cicle.objects.create(grau="CFGS", codi="DAW", nom="DAW")
        self.profe = _usuari("profe")
        self.anna = _usuari("anna")
        self.biel = _usuari("biel")
        self.carla = _usuari("carla")
        self.extern = _usuari("extern")
        avui = datetime.date.today()
        self.projecte = Projecte.objects.create(
            nom="Projecte Kanban",
            cicle=self.cicle,
            inici=avui,
            final=avui + datetime.timedelta(days=30),
        )
        self.projecte.admins.add(self.profe)
        self.sprint = Sprint.objects.create(
            nom="Sprint 1",
            projecte=self.projecte,
            inici=avui,
            final=avui + datetime.timedelta(days=7),
        )
        self.mp1 = ModulProfessional.objects.create(numero=6, nom="Client", cicle=self.cicle)
        self.mp2 = ModulProfessional.objects.create(numero=7, nom="Servidor", cicle=self.cicle)
        self.specs = []
        for ordre in range(1, 7):
            spec = Spec.objects.create(
                nom="Tasca {}".format(ordre),
                projecte=self.projecte,
                ordre=ordre * 10,
                hores_estimades=4,
            )
            spec.mp.add(self.mp1 if ordre % 2 else self.mp2)
            self.specs.append(spec)
        self.specs[0].sprints.add(self.sprint)
        self.spec = self.specs[0]
        self.equip = Equip.objects.create(nom="Equip Alfa", projecte=self.projecte)
        self.equip.membres.set([self.anna, self.biel, self.carla])

    def entra(self, usuari):
        self.client.logout()
        self.client.login(username=usuari.email, password="contrasenya123")

    def url(self, nom, spec=None):
        args = [self.equip.id] + ([(spec or self.spec).id] if nom != "tauler" else [])
        return reverse(nom, args=args)

    def mou(self, usuari, estat, spec=None, motiu="", rol=kanban.MEMBRE, equip=None):
        return kanban.mou(equip or self.equip, spec or self.spec, usuari, rol, estat, motiu)

    def tasca(self, spec=None):
        return TascaEquip.objects.get(equip=self.equip, spec=spec or self.spec)

    def finalitza(self, spec, responsable, revisor):
        self.mou(responsable, kanban.EN_CURS, spec)
        self.mou(responsable, kanban.TEST, spec)
        self.mou(revisor, kanban.FINALITZAT, spec)


class EstatsTests(BaseKanban):
    def test_una_tasca_sense_tocar_es_pendent(self):
        columnes = kanban.dades_tauler(self.equip, kanban.MEMBRE)
        self.assertEqual([c["estat"] for c in columnes], kanban.ESTATS)
        self.assertEqual(len(columnes[0]["targetes"]), 6)
        self.assertFalse(TascaEquip.objects.exists())

    def test_qui_comenca_una_tasca_en_queda_responsable(self):
        self.mou(self.anna, kanban.EN_CURS)
        tasca = self.tasca()
        self.assertEqual(tasca.estat, kanban.EN_CURS)
        self.assertEqual(tasca.responsable, self.anna)
        tipus = list(tasca.events.values_list("tipus", flat=True))
        self.assertEqual(tipus, [TascaEvent.RESPONSABLE, TascaEvent.ESTAT])

    def test_no_es_pot_saltar_de_pendent_a_finalitzat(self):
        with self.assertRaises(kanban.ErrorKanban):
            self.mou(self.anna, kanban.FINALITZAT)

    def test_bloquejar_demana_el_motiu(self):
        self.mou(self.anna, kanban.EN_CURS)
        with self.assertRaises(kanban.ErrorKanban):
            self.mou(self.anna, kanban.BLOQUEJAT, motiu="   ")
        self.assertEqual(self.tasca().estat, kanban.EN_CURS)
        self.mou(self.anna, kanban.BLOQUEJAT, motiu="Falta el servidor")
        bloqueig = TascaBloqueig.objects.get()
        self.assertEqual(bloqueig.motiu, "Falta el servidor")
        self.assertIsNone(bloqueig.tancat_el)

    def test_desbloquejar_torna_a_l_estat_d_on_venia(self):
        self.mou(self.anna, kanban.EN_CURS)
        self.mou(self.anna, kanban.TEST)
        self.mou(self.biel, kanban.BLOQUEJAT, motiu="No arrenca")
        self.assertEqual(kanban.transicions(self.tasca(), kanban.MEMBRE), [kanban.TEST])
        with self.assertRaises(kanban.ErrorKanban):
            self.mou(self.biel, kanban.EN_CURS)
        # Qualsevol membre desbloqueja, i es recorda qui l'havia enviada a Test.
        self.mou(self.carla, kanban.TEST)
        tasca = self.tasca()
        self.assertEqual(tasca.estat, kanban.TEST)
        self.assertEqual(tasca.enviada_a_test_per, self.anna)
        bloqueig = TascaBloqueig.objects.get()
        self.assertEqual(bloqueig.tancat_per, self.carla)
        self.assertIsNotNone(bloqueig.tancat_el)

    def test_nomes_la_persona_responsable_envia_a_test(self):
        self.mou(self.anna, kanban.EN_CURS)
        with self.assertRaises(kanban.ErrorKanban):
            self.mou(self.biel, kanban.TEST)
        self.mou(self.anna, kanban.TEST)
        self.assertEqual(self.tasca().estat, kanban.TEST)

    def test_la_persona_responsable_no_pot_validar_la_seva_tasca(self):
        self.mou(self.anna, kanban.EN_CURS)
        self.mou(self.anna, kanban.TEST)
        with self.assertRaises(kanban.ErrorKanban):
            self.mou(self.anna, kanban.FINALITZAT)
        self.mou(self.biel, kanban.FINALITZAT)
        tasca = self.tasca()
        self.assertEqual(tasca.estat, kanban.FINALITZAT)
        self.assertEqual(tasca.validada_per, self.biel)
        self.assertEqual(tasca.responsable, self.anna)
        self.assertIsNotNone(tasca.finalitzada_el)

    def test_no_es_pot_traspassar_a_test_per_validar_la_feina_propia(self):
        self.mou(self.anna, kanban.EN_CURS)
        self.mou(self.anna, kanban.TEST)
        with self.assertRaises(kanban.ErrorKanban):
            kanban.canvia_responsable(
                self.equip, self.spec, self.anna, kanban.MEMBRE, self.biel
            )
        # Encara que el professorat la reassigni, qui l'ha enviada no la valida.
        kanban.canvia_responsable(
            self.equip, self.spec, self.profe, kanban.PROFE, self.biel
        )
        for persona in (self.anna, self.biel):
            with self.assertRaises(kanban.ErrorKanban):
                self.mou(persona, kanban.FINALITZAT)
        self.mou(self.carla, kanban.FINALITZAT)

    def test_un_equip_d_una_persona_valida_les_seves_tasques(self):
        sol = Equip.objects.create(nom="Sol", projecte=self.projecte)
        sol.membres.set([self.anna])
        for estat in (kanban.EN_CURS, kanban.TEST, kanban.FINALITZAT):
            self.mou(self.anna, estat, equip=sol)
        self.assertEqual(
            TascaEquip.objects.get(equip=sol).estat, kanban.FINALITZAT
        )

    def test_el_professorat_pot_corregir_qualsevol_estat(self):
        self.mou(self.profe, kanban.FINALITZAT, rol=kanban.PROFE)
        tasca = self.tasca()
        self.assertEqual(tasca.estat, kanban.FINALITZAT)
        self.assertIsNone(tasca.responsable)
        self.mou(self.profe, kanban.PENDENT, rol=kanban.PROFE)
        self.assertIsNone(self.tasca().finalitzada_el)

    def test_reobrir_una_tasca_finalitzada(self):
        self.finalitza(self.spec, self.anna, self.biel)
        self.mou(self.carla, kanban.EN_CURS)
        tasca = self.tasca()
        self.assertEqual(tasca.estat, kanban.EN_CURS)
        self.assertIsNone(tasca.validada_per)
        self.assertEqual(tasca.responsable, self.anna)

    def test_qui_no_es_de_l_equip_no_pot_moure_tasques(self):
        with self.assertRaises(kanban.ErrorKanban):
            self.mou(self.extern, kanban.EN_CURS, rol=kanban.rol(self.extern, self.equip))


class PersonesTests(BaseKanban):
    def test_traspas_de_responsabilitat(self):
        self.mou(self.anna, kanban.EN_CURS)
        with self.assertRaises(kanban.ErrorKanban):
            kanban.canvia_responsable(
                self.equip, self.spec, self.biel, kanban.MEMBRE, self.biel
            )
        with self.assertRaises(kanban.ErrorKanban):
            kanban.canvia_responsable(
                self.equip, self.spec, self.anna, kanban.MEMBRE, self.extern
            )
        kanban.canvia_responsable(
            self.equip, self.spec, self.anna, kanban.MEMBRE, self.biel
        )
        self.assertEqual(self.tasca().responsable, self.biel)

    def test_colaboradors(self):
        self.mou(self.anna, kanban.EN_CURS)
        afegeix = lambda qui, persona: kanban.canvia_colaborador(
            self.equip, self.spec, qui, kanban.MEMBRE, persona, afegeix=True
        )
        with self.assertRaises(kanban.ErrorKanban):
            afegeix(self.biel, self.carla)  # no és la persona responsable
        with self.assertRaises(kanban.ErrorKanban):
            afegeix(self.anna, self.anna)  # la responsable no col·labora
        with self.assertRaises(kanban.ErrorKanban):
            afegeix(self.anna, self.extern)  # no és de l'equip
        afegeix(self.anna, self.biel)
        self.assertEqual(list(self.tasca().colaboradors.all()), [self.biel])
        # Si el col·laborador passa a ser responsable, deixa de ser col·laborador.
        kanban.canvia_responsable(
            self.equip, self.spec, self.anna, kanban.MEMBRE, self.biel
        )
        self.assertFalse(self.tasca().colaboradors.exists())

    def test_una_tasca_sense_responsable_no_te_colaboradors(self):
        with self.assertRaises(kanban.ErrorKanban):
            kanban.canvia_colaborador(
                self.equip, self.spec, self.profe, kanban.PROFE, self.biel, afegeix=True
            )

    def test_qui_deixa_l_equip_perd_les_tasques_obertes(self):
        self.mou(self.anna, kanban.EN_CURS)
        self.finalitza(self.specs[1], self.anna, self.biel)
        self.equip.membres.remove(self.anna)
        kanban.dades_tauler(self.equip, kanban.MEMBRE)
        self.assertIsNone(self.tasca().responsable)
        # La feina acabada conserva qui la va fer.
        self.assertEqual(self.tasca(self.specs[1]).responsable, self.anna)
        # Una persona de l'equip pot assumir la tasca que ha quedat òrfena.
        kanban.canvia_responsable(
            self.equip, self.spec, self.biel, kanban.MEMBRE, self.biel
        )
        self.assertEqual(self.tasca().responsable, self.biel)

    def test_comentaris_de_seguiment(self):
        with self.assertRaises(kanban.ErrorKanban):
            kanban.comenta(self.equip, self.spec, self.anna, kanban.MEMBRE, "  ")
        with self.assertRaises(kanban.ErrorKanban):
            kanban.comenta(self.equip, self.spec, self.extern, kanban.PUBLIC, "Hola")
        kanban.comenta(self.equip, self.spec, self.anna, kanban.MEMBRE, "Va bé")
        kanban.comenta(self.equip, self.spec, self.profe, kanban.PROFE, "Endavant")
        self.assertEqual(self.tasca().comentaris.count(), 2)


class VistesTests(BaseKanban):
    def test_la_targeta_mostra_el_numero_de_la_tasca(self):
        self.entra(self.anna)
        resposta = self.client.get(self.url("tauler"))
        self.assertContains(resposta, '<span class="task-num">10.</span> Tasca 1', html=False)
        self.assertContains(resposta, "Sprint 1")
        self.assertContains(resposta, "Backlog")
        self.assertContains(resposta, "4 hores")
        for nom in ("Pendent", "En curs", "Bloquejat", "Test", "Finalitzat"):
            self.assertContains(resposta, nom)

    def test_vista_publica_sense_noms_ni_textos(self):
        self.mou(self.anna, kanban.EN_CURS)
        self.mou(self.anna, kanban.BLOQUEJAT, motiu="Motiu secret")
        kanban.comenta(self.equip, self.spec, self.biel, kanban.MEMBRE, "Comentari intern")
        for usuari in (None, self.extern):
            self.client.logout()
            if usuari:
                self.entra(usuari)
            for url in (self.url("tauler"), self.url("tasca_detall")):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "Tasca 1")
                for secret in ("Anna", "Biel", "Carla", "Motiu secret", "Comentari intern", "anna@"):
                    self.assertNotContains(resposta, secret)

    def test_els_membres_i_el_professorat_ho_veuen_tot(self):
        self.mou(self.anna, kanban.EN_CURS)
        self.mou(self.anna, kanban.BLOQUEJAT, motiu="Motiu visible")
        for usuari in (self.biel, self.profe):
            self.entra(usuari)
            resposta = self.client.get(self.url("tauler"))
            self.assertContains(resposta, "Anna Prova")
            self.assertContains(resposta, "Motiu visible")

    def test_el_professorat_entra_en_nomes_lectura(self):
        self.entra(self.profe)
        resposta = self.client.get(self.url("tauler"))
        self.assertContains(resposta, 'id="permet-edicio"')
        self.entra(self.anna)
        self.assertNotContains(self.client.get(self.url("tauler")), 'id="permet-edicio"')

    def test_moure_per_http(self):
        self.entra(self.anna)
        resposta = self.client.post(self.url("tasca_mou"), {"estat": "en_curs"})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["ok"])
        self.assertIn("Anna Prova", resposta.json()["html"])
        resposta = self.client.post(self.url("tasca_mou"), {"estat": "bloquejat"})
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("per què", resposta.json()["error"])

    def test_accions_per_http_sense_permis(self):
        self.client.logout()
        resposta = self.client.post(self.url("tasca_mou"), {"estat": "en_curs"})
        self.assertEqual(resposta.status_code, 302)
        self.entra(self.extern)
        for nom, dades in (
            ("tasca_mou", {"estat": "en_curs"}),
            ("tasca_comentari", {"text": "Hola"}),
            ("tasca_responsable", {"usuari": self.extern.pk}),
            ("tasca_colaborador", {"usuari": self.extern.pk}),
        ):
            resposta = self.client.post(self.url(nom), dades)
            self.assertEqual(resposta.status_code, 400, nom)
        self.assertFalse(TascaEvent.objects.exists())

    def test_la_qualificacio_del_professorat_es_veu_a_la_targeta(self):
        qualificacio = Qualificacio.objects.create(equip=self.equip, sprint=self.sprint)
        DoneSpec.objects.create(qualificacio=qualificacio, spec=self.spec, percentatge=60)
        self.entra(self.anna)
        resposta = self.client.get(self.url("tauler"))
        self.assertContains(resposta, "Qualificada pel professorat")
        self.assertContains(resposta, "60%")

    @override_settings(KANBAN_POLL_SECONDS=17)
    def test_refresc_automatic_configurable(self):
        self.entra(self.anna)
        self.assertContains(self.client.get(self.url("tauler")), 'data-interval="17"')
        versio = reverse("tauler_versio", args=[self.equip.id])
        abans = self.client.get(versio).json()["versio"]
        self.mou(self.anna, kanban.EN_CURS)
        self.assertGreater(self.client.get(versio).json()["versio"], abans)

    def test_matriu_i_bloquejades_nomes_per_al_professorat(self):
        self.mou(self.anna, kanban.EN_CURS)
        self.mou(self.anna, kanban.BLOQUEJAT, motiu="Sense connexió")
        matriu = reverse("matriu_projecte", args=[self.projecte.id])
        bloquejades = reverse("tasques_bloquejades")
        self.entra(self.anna)
        self.assertEqual(self.client.get(matriu).status_code, 404)
        self.assertEqual(self.client.get(bloquejades).status_code, 404)
        self.entra(self.profe)
        self.assertContains(self.client.get(matriu), "Equip Alfa")
        resposta = self.client.get(bloquejades)
        self.assertContains(resposta, "Sense connexió")
        self.assertContains(resposta, "Tasca 1")

    def test_el_projecte_enllaca_els_taulers(self):
        resposta = self.client.get(reverse("projecte", args=[self.projecte.id]))
        self.assertContains(resposta, self.url("tauler"))


class InsigniesVistaTests(BaseKanban):
    def setUp(self):
        super().setUp()
        self.url_insignies = reverse("insignies_projecte", args=[self.projecte.id])

    def test_visibles_per_defecte_per_a_l_alumnat_del_projecte(self):
        self.assertTrue(self.projecte.insignies_visibles)
        self.entra(self.anna)
        resposta = self.client.get(self.url_insignies)
        self.assertContains(resposta, "Tothom revisa")
        self.assertContains(resposta, "El teu equip")
        # No es mostra qui forma part dels equips.
        self.assertNotContains(resposta, "Biel")

    def test_amagades_nomes_les_veu_el_professorat(self):
        self.projecte.insignies_visibles = False
        self.projecte.save()
        self.entra(self.anna)
        self.assertEqual(self.client.get(self.url_insignies).status_code, 404)
        self.assertNotContains(self.client.get(self.url("tauler")), self.url_insignies)
        self.entra(self.profe)
        self.assertEqual(self.client.get(self.url_insignies).status_code, 200)

    def test_qui_no_es_del_projecte_no_les_veu(self):
        self.entra(self.extern)
        self.assertEqual(self.client.get(self.url_insignies).status_code, 404)

    def test_es_configura_des_del_formulari_del_projecte(self):
        self.entra(self.profe)
        url = reverse("edita_projecte", args=[self.projecte.id])
        self.assertContains(self.client.get(url), 'name="insignies_visibles"')
        dades = {
            "nom": self.projecte.nom,
            "inici": self.projecte.inici.isoformat(),
            "final": self.projecte.final.isoformat(),
            "insignies_presents": "1",
        }
        self.client.post(url, dades)
        self.projecte.refresh_from_db()
        self.assertFalse(self.projecte.insignies_visibles)
        self.client.post(url, dict(dades, insignies_visibles="on"))
        self.projecte.refresh_from_db()
        self.assertTrue(self.projecte.insignies_visibles)

    def test_clonar_copia_la_configuracio_pero_no_el_tauler(self):
        self.projecte.insignies_visibles = False
        self.projecte.save()
        self.mou(self.anna, kanban.EN_CURS)
        clon = _clona_projecte(self.projecte, "Clon", self.profe)
        self.assertFalse(clon.insignies_visibles)
        self.assertFalse(TascaEquip.objects.filter(spec__projecte=clon).exists())


class InsigniesCalculTests(BaseKanban):
    def insignies(self):
        return {i["clau"]: i for i in insignies.de_l_equip(self.equip)}

    def test_no_compten_fins_a_una_tasca_per_persona(self):
        self.finalitza(self.specs[0], self.anna, self.biel)
        dades = self.insignies()
        self.assertFalse(dades["tothom_tasques"]["aconseguida"])
        self.assertIn("Encara no compta", dades["tothom_tasques"]["progres"])

    def test_equip_que_ho_reparteix_tot_les_te_totes(self):
        # Cadascú fa dues tasques (un mòdul de cada) i valida les del següent.
        ordre = [self.anna, self.biel, self.carla]
        for index, spec in enumerate(self.specs):
            responsable = ordre[index % 3]
            revisor = ordre[(index + 1) % 3]
            self.finalitza(spec, responsable, revisor)
        dades = self.insignies()
        for clau, insignia in dades.items():
            self.assertTrue(insignia["aconseguida"], clau)
            self.assertEqual(insignia["no_disponible"], "", clau)

    def test_el_merit_es_de_la_persona_responsable_no_de_qui_valida(self):
        # L'Anna ho fa tot; en Biel i la Carla només validen.
        for index, spec in enumerate(self.specs[:4]):
            self.finalitza(spec, self.anna, self.biel if index % 2 else self.carla)
        dades = self.insignies()
        self.assertFalse(dades["tothom_tasques"]["aconseguida"])
        self.assertFalse(dades["repartida_tasques"]["aconseguida"])
        self.assertFalse(dades["tothom_hores"]["aconseguida"])
        self.assertFalse(dades["repartida_hores"]["aconseguida"])

    def test_les_hores_poden_dir_una_cosa_diferent_de_les_tasques(self):
        self.specs[0].hores_estimades = 40
        self.specs[0].save()
        ordre = [self.anna, self.biel, self.carla]
        for index, spec in enumerate(self.specs):
            self.finalitza(spec, ordre[index % 3], ordre[(index + 1) % 3])
        dades = self.insignies()
        self.assertTrue(dades["repartida_tasques"]["aconseguida"])
        self.assertFalse(dades["repartida_hores"]["aconseguida"])

    def test_tothom_revisa_es_perd_si_sempre_valida_la_mateixa_persona(self):
        ordre = [self.anna, self.biel, self.carla]
        for index, spec in enumerate(self.specs):
            responsable = ordre[index % 3]
            revisor = self.anna if responsable != self.anna else self.biel
            self.finalitza(spec, responsable, revisor)
        self.assertFalse(self.insignies()["tothom_revisa"]["aconseguida"])

    def test_no_disponibles(self):
        dades = self.insignies()
        self.assertEqual(dades["polivalents"]["no_disponible"], "")
        # Menys de tres persones: no hi ha a qui repartir les revisions.
        self.equip.membres.remove(self.carla)
        self.assertTrue(self.insignies()["tothom_revisa"]["no_disponible"])
        # Una sola persona: tampoc hi ha feina per repartir.
        self.equip.membres.remove(self.biel)
        dades = self.insignies()
        self.assertTrue(dades["repartida_tasques"]["no_disponible"])
        self.assertEqual(dades["tothom_tasques"]["no_disponible"], "")
        # Un sol mòdul al projecte i cap hora estimada.
        for spec in self.specs:
            spec.mp.set([self.mp1])
        Spec.objects.filter(projecte=self.projecte).update(hores_estimades=0)
        dades = self.insignies()
        self.assertTrue(dades["polivalents"]["no_disponible"])
        self.assertTrue(dades["tothom_hores"]["no_disponible"])

    def test_qui_deixa_l_equip_no_compta(self):
        ordre = [self.anna, self.biel, self.carla]
        for index, spec in enumerate(self.specs):
            self.finalitza(spec, ordre[index % 3], ordre[(index + 1) % 3])
        self.equip.membres.remove(self.carla)
        dades = self.insignies()
        # Queden 4 tasques entre 2 persones, 2 per cap: segueix repartit.
        self.assertTrue(dades["tothom_tasques"]["aconseguida"])
        self.assertIn("2 tasques", dades["tothom_tasques"]["progres"])
