"""Honey-Stack - Controllo periodico delle esche.

Ogni check_interval secondi verifica in Keystone che ogni esca attiva:
- esista ancora (se qualcuno l'ha cancellata: allarme, esca disattivata);
- sia abilitata (se qualcuno l'ha disabilitata: allarme e riattivazione);
- non abbia ruoli ne' gruppi (un ruolo trasforma l'esca in un accesso
  vero al cloud: allarme e rimozione del ruolo o del gruppo).
Gira dentro il watcher, in un thread separato.
"""
import uuid
from datetime import datetime, timezone

from honeystack import cloud as cloud_mod
from honeystack import config, db

LOG = config.logging.getLogger(__name__)


def _allarme(esca, tipo, dettaglio):
    """Salva un allarme del controllo; IP e strumento non ci sono."""
    db.save_alert(event_id="controllo-" + uuid.uuid4().hex,
                  user_id=esca["user_id"], name=esca["name"],
                  outcome=tipo, source_ip=None, agent=dettaglio,
                  event_time=datetime.now(timezone.utc).isoformat())
    LOG.warning("ALLARME CONTROLLO: honeytoken=%s tipo=%s %s",
                esca["name"], tipo, dettaglio)


def controlla_esca(esca, cloud):
    """Controlla una sola esca e ripara quello che si puo' riparare."""
    user_id = esca["user_id"]
    stato = cloud.stato_utente(user_id)
    if stato == "assente":
        _allarme(esca, "esca_eliminata",
                 "utente cancellato da Keystone fuori da Honey-Stack")
        db.disable_honeytoken(user_id)
        return
    if stato == "disattivato":
        _allarme(esca, "esca_disattivata",
                 "utente disabilitato in Keystone: riattivato")
        cloud.riattiva_utente(user_id)
    for ruolo in cloud.ruoli_utente(user_id):
        _allarme(esca, "ruolo_assegnato",
                 "ruolo %s su %s %s: rimosso" % (
                     ruolo["ruolo"], ruolo["ambito"], ruolo["ambito_nome"]))
        cloud.rimuovi_ruolo(user_id, ruolo)
    for gruppo in cloud.gruppi_utente(user_id):
        _allarme(esca, "gruppo_assegnato",
                 "inserito nel gruppo %s: tolto" % gruppo["nome"])
        cloud.rimuovi_da_gruppo(user_id, gruppo["id"])


def controlla_esche(cloud=None):
    """Controlla tutte le esche attive; un errore non ferma le altre."""
    cloud = cloud or cloud_mod.Cloud()
    for esca in db.list_honeytokens():
        try:
            controlla_esca(esca, cloud)
        except Exception:
            LOG.exception("Controllo dell'esca %s non riuscito", esca["name"])


def ciclo(fermati, intervallo=None):
    """Scheduler: un controllo subito, poi uno ogni intervallo secondi."""
    intervallo = intervallo or config.get("check_interval")
    cloud = cloud_mod.Cloud()
    LOG.info("Controllo periodico delle esche ogni %s s", intervallo)
    while True:
        controlla_esche(cloud)
        if fermati.wait(intervallo):
            return
