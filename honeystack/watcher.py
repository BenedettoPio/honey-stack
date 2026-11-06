"""Honey-Stack - Watcher.

Ascolta le notifiche CADF di Keystone su RabbitMQ, riconosce gli
honeytoken registrati nel database e salva un allarme per ogni
tentativo di autenticazione.
Avvio: honey-stack-watcher
"""
import configparser
import json
import signal
import sys
import threading

from oslo_config import cfg
import oslo_messaging

from honeystack import config, controllo, correlazione, db

LOG = config.logging.getLogger(__name__)


def leggi_transport_url(path=None):
    """Legge l'indirizzo di RabbitMQ dalla configurazione di Keystone."""
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.read(path or config.get("keystone_conf"))
    return parser.get("oslo_messaging_notifications", "transport_url",
                      fallback=None)


class AuthEndpoint:
    """Riceve solo gli eventi di autenticazione di Keystone."""

    filter_rule = oslo_messaging.NotificationFilter(
        event_type=r"^identity\.authenticate$")

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        try:
            self._gestisci(payload)
        except Exception:
            LOG.exception("Errore nella gestione di un evento")

    def _gestisci(self, payload):
        # con debug = True nel file di configurazione si vede l'evento
        # CADF completo: serve a raccogliere i dati per i test
        LOG.debug("Evento CADF: %s", json.dumps(payload))
        initiator = payload.get("initiator", {})
        user_id = initiator.get("user_id") or initiator.get("id")
        honeytoken = db.get_active_honeytoken(user_id)
        if honeytoken is None:
            return
        host = initiator.get("host", {})
        nuovo = db.save_alert(
            event_id=payload.get("id"),
            user_id=user_id,
            name=honeytoken["name"],
            outcome=payload.get("outcome"),
            source_ip=host.get("address"),
            agent=host.get("agent"),
            event_time=payload.get("eventTime"),
        )
        if nuovo:
            LOG.warning("ALLARME: honeytoken=%s esito=%s ip=%s agente=%s "
                        "ora=%s", honeytoken["name"], payload.get("outcome"),
                        host.get("address"), host.get("agent"),
                        payload.get("eventTime"))
            correlazione.analizza(host.get("address"))


def main():
    config.setup_log()
    url = leggi_transport_url()
    if not url:
        LOG.error("Notifiche di Keystone non configurate: manca "
                  "transport_url in [oslo_messaging_notifications] di %s",
                  config.get("keystone_conf"))
        sys.exit(1)
    db.connect().close()
    config.attendi(url, "RabbitMQ", porta_predefinita=5672)

    fermati = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: fermati.set())
    signal.signal(signal.SIGINT, lambda *_: fermati.set())

    transport = oslo_messaging.get_notification_transport(cfg.CONF, url=url)
    targets = [oslo_messaging.Target(topic="notifications",
                                     exchange="keystone")]
    listener = oslo_messaging.get_notification_listener(
        transport, targets, [AuthEndpoint()],
        executor="threading", pool="honeystack")
    listener.start()
    LOG.info("Honey-Stack watcher in ascolto... (Ctrl+C per uscire)")
    scheduler = threading.Thread(target=controllo.ciclo, args=(fermati,),
                                 name="controllo-esche", daemon=True)
    scheduler.start()
    while not fermati.wait(1):
        pass
    LOG.info("Arresto del watcher...")
    listener.stop()
    listener.wait()
    scheduler.join(timeout=10)


if __name__ == "__main__":
    main()
