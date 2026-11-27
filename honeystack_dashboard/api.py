"""Client delle API REST di Honey-Stack usato dai pannelli di Horizon.
 
L'indirizzo delle API si legge dal catalogo di Keystone (servizio di
tipo "deception") e ogni richiesta porta il token dell'utente entrato
in Horizon: Honey-Stack lo verifica su Keystone e chiede il ruolo admin.
"""
from urllib.parse import quote
 
from django.conf import settings
import requests
 
from openstack_dashboard.api import base
 
# ==================================================================
# Impostazioni
# ==================================================================
 
# tipo del servizio nel catalogo di Keystone e attesa massima
TIPO_SERVIZIO = "deception"
ATTESA = 10  # secondi
 
 
# ==================================================================
# Chiamata alle API (l'unico punto che parla con Honey-Stack)
# ==================================================================
 
 
class Errore(Exception):
    """Risposta di errore delle API, con il messaggio di Honey-Stack."""
 
 
def _richiesta(request, metodo, percorso, **kwargs):
    """Chiama le API con il token dell'utente; un errore diventa Errore."""
    indirizzo = base.url_for(request, TIPO_SERVIZIO).rstrip("/") + percorso
    verifica = getattr(settings, "OPENSTACK_SSL_CACERT", None) or \
        not getattr(settings, "OPENSTACK_SSL_NO_VERIFY", False)
    risposta = requests.request(
        metodo, indirizzo, timeout=ATTESA, verify=verifica,
        headers={"X-Auth-Token": request.user.token.id}, **kwargs)
    if risposta.status_code >= 400:
        try:
            messaggio = risposta.json()["error"]
        except (ValueError, KeyError, TypeError):
            messaggio = "HTTP %s" % risposta.status_code
        raise Errore(messaggio)
    return risposta
 
 
# ==================================================================
# Una riga delle tabelle di Horizon
# ==================================================================
 
 
class Voce:
    """Riga di una tabella di Horizon: i campi diventano attributi."""
 
    def __init__(self, dati, chiave):
        self.__dict__.update(dati)
        self.id = dati[chiave]
 
 
# ==================================================================
# Funzioni usate dai pannelli, una per ogni API
# ==================================================================
 
 
def allarmi(request):
    """Ultimi allarmi (pannello Allarmi)."""
    return [Voce(a, "id") for a in
            _richiesta(request, "GET", "/api/v1/alerts").json()]
 
 
def esche(request):
    """Esche attive (pannello Honeytoken)."""
    return [Voce(h, "name") for h in
            _richiesta(request, "GET", "/api/v1/honeytokens").json()]
 
 
def crea_esca(request, nome, luogo=""):
    """Crea un'esca (finestra Crea honeytoken)."""
    return Voce(_richiesta(request, "POST", "/api/v1/honeytokens",
                           json={"name": nome, "location": luogo}).json(),
                "name")
 
 
def elimina_esca(request, nome):
    """Elimina un'esca (azione Elimina honeytoken)."""
    _richiesta(request, "DELETE", "/api/v1/honeytokens/%s" % quote(nome))
 
 
def file_esca(request, nome, file):
    """Contenuto di clouds.yaml o openrc (azioni Scarica)."""
    return _richiesta(request, "GET", "/api/v1/honeytokens/%s/files/%s"
                      % (quote(nome), file)).content
 
 
def quarantene(request):
    """Quarantene attive (pannello Quarantene)."""
    return [Voce(q, "id") for q in
            _richiesta(request, "GET", "/api/v1/quarantines").json()]
 
 
def rilascia(request, voce):
    """Rilascia una VM (azione Rilascia VM); restituisce il suo nome."""
    return _richiesta(request, "POST", "/api/v1/quarantines/%s/release"
                      % voce).json()["server_name"]
 
