"""Test dei pannelli di Horizon con le API di Honey-Stack finte.

Avvio (serve Horizon installato):
  DJANGO_SETTINGS_MODULE=honeystack_dashboard.tests.settings \
      python -m django test honeystack_dashboard.tests
"""
from unittest import mock

from django.urls import reverse

from openstack_dashboard.test import helpers

API = "http://public.honeystack.example.com:5050"
INDICE_ESCHE = reverse("horizon:admin:honeytokens:index")


def risposta(stato=200, dati=None, contenuto=b""):
    r = mock.Mock(status_code=stato, content=contenuto)
    r.json.return_value = dati
    return r


class PannelliHoneyStack(helpers.BaseAdminViewTests):

    def _setup_test_data(self):
        super()._setup_test_data()
        self.service_catalog.append({
            "type": "deception", "name": "honey-stack",
            "endpoints_links": [],
            "endpoints": [{"region": "RegionOne", "interface": "public",
                           "url": API}]})

    def setUp(self):
        super().setUp()
        patcher = mock.patch("honeystack_dashboard.api.requests.request")
        self.richiesta = patcher.start()
        self.addCleanup(patcher.stop)

    def chiamata(self, n=0):
        args, kwargs = self.richiesta.call_args_list[n]
        return args[0], args[1], kwargs

    def test_allarmi(self):
        self.richiesta.return_value = risposta(dati=[{
            "id": 1, "name": "svc_backup", "outcome": "success",
            "gravita": "GRAVE", "luogo": "Kali ~/Downloads",
            "source_ip": "192.168.206.129", "agent": "openstacksdk",
            "event_time": "2026-11-16T10:00:00.000000+0000"}])
        pagina = self.client.get(reverse("horizon:admin:alerts:index"))
        self.assertEqual(pagina.status_code, 200)
        self.assertTemplateUsed(pagina, "admin/alerts/index.html")
        self.assertContains(pagina, "svc_backup")
        self.assertContains(pagina, "label-danger")
        self.assertContains(pagina, "2026-11-16 10:00:00")
        metodo, indirizzo, kwargs = self.chiamata()
        self.assertEqual((metodo, indirizzo), ("GET", API + "/api/v1/alerts"))
        self.assertEqual(kwargs["headers"]["X-Auth-Token"], self.token.id)

    def test_errore_delle_api_non_rompe_la_pagina(self):
        self.richiesta.return_value = risposta(401, {"error": "no"})
        pagina = self.client.get(reverse("horizon:admin:alerts:index"))
        self.assertEqual(pagina.status_code, 200)
        self.assertMessageCount(pagina, error=1)

    def test_elenco_honeytoken(self):
        self.richiesta.return_value = risposta(dati=[{
            "name": "svc_backup", "luogo": "repo Git",
            "created_at": "2026-11-16T09:00:00"}])
        pagina = self.client.get(INDICE_ESCHE)
        self.assertContains(pagina, "svc_backup")
        self.assertContains(pagina, "repo Git")
        self.assertContains(pagina, reverse(
            "horizon:admin:honeytokens:download",
            args=["svc_backup", "clouds.yaml"]))

    def test_crea_honeytoken(self):
        self.richiesta.return_value = risposta(201, {"name": "svc_backup"})
        pagina = self.client.post(
            reverse("horizon:admin:honeytokens:create"),
            {"name": "svc_backup", "location": "repo Git"})
        self.assertNoFormErrors(pagina)
        self.assertRedirectsNoFollow(pagina, INDICE_ESCHE)
        metodo, indirizzo, kwargs = self.chiamata()
        self.assertEqual((metodo, indirizzo),
                         ("POST", API + "/api/v1/honeytokens"))
        self.assertEqual(kwargs["json"],
                         {"name": "svc_backup", "location": "repo Git"})

    def test_nome_non_valido_non_chiama_le_api(self):
        pagina = self.client.post(
            reverse("horizon:admin:honeytokens:create"),
            {"name": "../etc", "location": ""})
        self.assertFormErrors(pagina, 1)
        self.richiesta.assert_not_called()

    def test_crea_honeytoken_duplicato(self):
        self.richiesta.return_value = risposta(
            409, {"error": "Esiste gia' un utente chiamato admin"})
        pagina = self.client.post(
            reverse("horizon:admin:honeytokens:create"),
            {"name": "admin", "location": ""})
        self.assertContains(pagina, "Esiste gia")

    def test_elimina_honeytoken(self):
        self.richiesta.side_effect = [
            risposta(dati=[{"name": "svc_backup", "luogo": "",
                            "created_at": "2026-11-16T09:00:00"}]),
            risposta(204)]
        pagina = self.client.post(
            INDICE_ESCHE, {"action": "esche__delete__svc_backup"})
        self.assertRedirectsNoFollow(pagina, INDICE_ESCHE)
        metodo, indirizzo, _ = self.chiamata(1)
        self.assertEqual((metodo, indirizzo),
                         ("DELETE", API + "/api/v1/honeytokens/svc_backup"))

    def test_scarica_file_esca(self):
        self.richiesta.return_value = risposta(contenuto=b"clouds:\n")
        pagina = self.client.get(reverse(
            "horizon:admin:honeytokens:download",
            args=["svc_backup", "clouds.yaml"]))
        self.assertEqual(pagina.content, b"clouds:\n")
        self.assertIn('filename="clouds.yaml"',
                      pagina["Content-Disposition"])
        self.assertEqual(self.chiamata()[1], API +
                         "/api/v1/honeytokens/svc_backup/files/clouds.yaml")

    def test_rilascia_vm(self):
        self.richiesta.side_effect = [
            risposta(dati=[{"id": 3, "server_name": "web-01",
                            "source_ip": "172.24.4.124",
                            "honeytoken": "svc_deploy",
                            "started_at": "2026-11-16T10:05:00"}]),
            risposta(dati={"server_name": "web-01"})]
        indice = reverse("horizon:admin:quarantines:index")
        pagina = self.client.post(
            indice, {"action": "quarantene__release__3"})
        self.assertRedirectsNoFollow(pagina, indice)
        metodo, indirizzo, _ = self.chiamata(1)
        self.assertEqual((metodo, indirizzo),
                         ("POST", API + "/api/v1/quarantines/3/release"))

    def test_pannelli_nascosti_senza_servizio_nel_catalogo(self):
        self.service_catalog.pop()
        self.setActiveUser(id=self.user.id, token=self.token,
                           username=self.user.name, tenant_id=self.tenant.id,
                           service_catalog=self.service_catalog,
                           authorized_tenants=self.tenants.list())
        pagina = self.client.get(reverse("horizon:admin:alerts:index"))
        self.assertNotEqual(pagina.status_code, 200)
        self.richiesta.assert_not_called()
