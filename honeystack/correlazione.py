"""Honey-Stack - Correlazione degli attacchi.

Dopo ogni nuovo allarme di autenticazione guarda gli allarmi recenti
dallo stesso IP (finestra di correlation_window secondi) e riconosce
due comportamenti:
- brute force: almeno brute_force_threshold password sbagliate;
- ricognizione: tentativi su due o piu' esche diverse, segno che
  l'attaccante ha trovato piu' file esca o sta provando nomi.
Per ogni comportamento e IP si genera un solo allarme per finestra.
"""
import uuid
from datetime import datetime, timedelta, timezone

from honeystack import config, db

LOG = config.logging.getLogger(__name__)


def _allarme(tipo, ip, nomi, dettaglio):
    db.save_alert(event_id="correlazione-" + uuid.uuid4().hex,
                  user_id="-", name=", ".join(nomi), outcome=tipo,
                  source_ip=ip, agent=dettaglio,
                  event_time=datetime.now(timezone.utc).isoformat())
    LOG.warning("ALLARME CORRELAZIONE: tipo=%s ip=%s esche=%s %s",
                tipo, ip, ", ".join(nomi), dettaglio)


def analizza(ip):
    """Controlla gli allarmi recenti da ip; restituisce i tipi generati."""
    if not ip:
        return []
    finestra = config.get("correlation_window")
    soglia = config.get("brute_force_threshold")
    inizio = (datetime.now(timezone.utc) - timedelta(seconds=finestra)
              ).isoformat(timespec="seconds")
    recenti = db.alerts_from_ip_since(ip, inizio)
    accessi = [a for a in recenti if a["outcome"] in ("success", "failure")]
    gia_segnalati = {a["outcome"] for a in recenti}
    minuti = finestra // 60 or 1
    generati = []

    falliti = [a for a in accessi if a["outcome"] == "failure"]
    if len(falliti) >= soglia and "brute_force" not in gia_segnalati:
        nomi = sorted({a["name"] for a in falliti})
        _allarme("brute_force", ip, nomi,
                 "%d password sbagliate in %d minuti" % (len(falliti), minuti))
        generati.append("brute_force")

    esche = sorted({a["name"] for a in accessi})
    if len(esche) >= 2 and "ricognizione" not in gia_segnalati:
        _allarme("ricognizione", ip, esche,
                 "%d esche diverse provate in %d minuti" % (len(esche), minuti))
        generati.append("ricognizione")
    return generati
