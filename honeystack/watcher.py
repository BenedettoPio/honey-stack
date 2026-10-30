"""Honey-Stack - Watcher.

Ascolta le notifiche CADF di Keystone su RabbitMQ, riconosce gli
honeytoken registrati nel database e salva un allarme per ogni
tentativo di autenticazione.
Avvio: python -m honeystack.watcher
"""
import configparser
import time

from oslo_config import cfg
import oslo_messaging

from honeystack import db

KEYSTONE_CONF = "/etc/keystone/keystone.conf"


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
            print("ALLARME: honeytoken={} esito={} ip={} agente={} "
                  "ora={}".format(honeytoken["name"], payload.get("outcome"),
                                  host.get("address"), host.get("agent"),
                                  payload.get("eventTime")), flush=True)


def main():
    db.connect().close()
    transport = oslo_messaging.get_notification_transport(
        cfg.CONF, url=leggi_transport_url())
    targets = [oslo_messaging.Target(topic="notifications",
                                     exchange="keystone")]
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
