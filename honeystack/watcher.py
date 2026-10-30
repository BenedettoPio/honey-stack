"""Honey-Stack - Watcher (prototipo).

Ascolta le notifiche CADF di Keystone su RabbitMQ e segnala
ogni tentativo di autenticazione con un honeytoken.
"""
import configparser
import time

from oslo_config import cfg
import oslo_messaging

KEYSTONE_CONF = "/etc/keystone/keystone.conf"

# Honeytoken da sorvegliare: per ora a mano, poi verranno dal database
HONEYTOKENS = {"backup_admin"}


def leggi_transport_url(path=KEYSTONE_CONF):
    """Legge l'indirizzo di RabbitMQ dalla configurazione di Keystone."""
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.read(path)
    return parser.get("oslo_messaging_notifications", "transport_url")


class AuthEndpoint:
    """Riceve solo gli eventi di autenticazione di Keystone."""

    filter_rule = oslo_messaging.NotificationFilter(
        event_type=r"^identity\.authenticate$")

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        initiator = payload.get("initiator", {})
        nome = initiator.get("name") or initiator.get("username")
        if nome not in HONEYTOKENS:
            return
        host = initiator.get("host", {})
        print("ALLARME: honeytoken={} esito={} ip={} agente={} ora={}".format(
            nome,
            payload.get("outcome"),
            host.get("address"),
            host.get("agent"),
            payload.get("eventTime"),
        ), flush=True)


def main():
    transport = oslo_messaging.get_notification_transport(
        cfg.CONF, url=leggi_transport_url())
    targets = [oslo_messaging.Target(topic="notifications", exchange="keystone")]
    listener = oslo_messaging.get_notification_listener(
        transport, targets, [AuthEndpoint()],
        executor="threading", pool="honeystack")
    listener.start()
    print("Honey-Stack watcher in ascolto... (Ctrl+C per uscire)", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        listener.stop()
        listener.wait()


if __name__ == "__main__":
    main()
