"""Honey-Stack - Quarantena delle VM compromesse.

Quando un'esca viene usata con la password giusta da un indirizzo che
appartiene a una VM del cloud (floating IP o IP fisso), quella VM e'
compromessa: Honey-Stack le toglie i security group e mette solo il
gruppo di quarantena, senza regole, che blocca tutto il traffico.
I gruppi originali restano salvati nel database e il rilascio li rimette.
La VM non viene spenta ne' cancellata: resta disponibile per le analisi.
"""
import json
import uuid
from datetime import datetime, timezone

from honeystack import cloud as cloud_mod
from honeystack import config, db

LOG = config.logging.getLogger(__name__)


def da_isolare(esito):
    """Vero se l'esito di un accesso all'esca fa scattare la quarantena."""
    if not config.get("quarantine_enabled"):
        return False
    return esito == "success" or (esito == "failure" and
                                  config.get("quarantine_on_failure"))


def isola(ip, esca, cloud=None):
    """Mette in quarantena la VM con indirizzo ip; restituisce il suo nome.

    Non fa nulla (e restituisce None) se l'IP non e' di una VM del cloud
    o se la VM e' gia' in quarantena. Un errore viene registrato senza
    fermare il watcher.
    """
    if not ip:
        return None
    try:
        cloud = cloud or cloud_mod.Cloud()
        porta = cloud.porta_da_ip(ip)
        if porta is None:
            LOG.info("Quarantena: %s non appartiene a una VM del cloud", ip)
            return None
        if db.active_quarantine_for_port(porta["port_id"]):
            return None
        vm = cloud.nome_vm(porta["server_id"])
        gruppo = cloud.gruppo_quarantena(
            config.get("quarantine_security_group"), porta["project_id"])
        # prima si salvano i gruppi originali, poi si isola la VM
        voce = db.add_quarantine(
            port_id=porta["port_id"], server_id=porta["server_id"],
            server_name=vm, source_ip=ip, honeytoken=esca,
            original_groups=json.dumps(porta["gruppi"]))
        try:
            cloud.imposta_gruppi(porta["port_id"], [gruppo])
        except Exception:
            db.delete_quarantine(voce)
            raise
        nomi = ", ".join(porta["nomi_gruppi"]) or "nessuno"
        db.save_alert(event_id="quarantena-" + uuid.uuid4().hex,
                      user_id="-", name=esca, outcome="quarantena",
                      source_ip=ip,
                      agent="VM %s isolata (gruppi originali: %s)" % (vm, nomi),
                      event_time=datetime.now(timezone.utc).isoformat())
        LOG.warning("QUARANTENA: VM %s (%s) isolata dopo l'uso dell'esca %s; "
                    "gruppi originali: %s", vm, ip, esca, nomi)
        return vm
    except Exception:
        LOG.exception("Quarantena della VM con IP %s non riuscita", ip)
        return None


def rilascia(vm_o_ip, cloud=None):
    """Rimette i gruppi originali alla VM in quarantena (nome o IP)."""
    voce = db.active_quarantine_for(vm_o_ip)
    if voce is None:
        raise ValueError(vm_o_ip + " non e' in quarantena")
    return rilascia_voce(voce, cloud)


def rilascia_voce(voce, cloud=None):
    cloud = cloud or cloud_mod.Cloud()
    cloud.imposta_gruppi(voce["port_id"], json.loads(voce["original_groups"]))
    db.release_quarantine(voce["id"])
    LOG.info("Quarantena: VM %s rilasciata, gruppi originali ripristinati",
             voce["server_name"])
    return voce["server_name"]
