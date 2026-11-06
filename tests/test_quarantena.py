"""Test della quarantena delle VM compromesse (quarantena.py).

Gli attacchi partono dagli eventi CADF reali catturati da Kali, con
l'IP cambiato in quello di una VM del cloud.
"""
import copy
import json

import pytest

from honeystack import cloud, config, db, manager, quarantena, watcher

FIP = "172.24.4.124"


@pytest.fixture
def quarantena_attiva():
    config.CONF.set_override("quarantine_enabled", True)
    yield
    config.CONF.clear_override("quarantine_enabled")
    config.CONF.clear_override("quarantine_on_failure")


@pytest.fixture
def cloud_con_vm(cloud_finto):
    """Una VM web-01 con floating IP e il gruppo honey-esca."""
    cloud_finto.porte[FIP] = {
        "port_id": "porta-1", "server_id": "vm-1", "project_id": "p-service",
        "gruppi": ["sg-esca"], "nomi_gruppi": ["honey-esca"]}
    cloud_finto.vm["vm-1"] = "web-01"
    cloud_finto.gruppi_porta["porta-1"] = ["sg-esca"]
    return cloud_finto


def attacco_dalla_vm(eventi, caso="esca_password_giusta", ip=FIP, n=0):
    evento = copy.deepcopy(eventi[caso])
    evento["id"] = "evento-vm-%d" % n
    evento["initiator"]["host"]["address"] = ip
    db.add_honeytoken(evento["initiator"]["user_id"], "svc_deploy", "p1",
                      "VM web-01")
    watcher.AuthEndpoint().info({}, "identity.keystone",
                                "identity.authenticate", evento, {})


def test_password_giusta_dalla_vm_la_isola(eventi, cloud_con_vm,
                                          quarantena_attiva):
    attacco_dalla_vm(eventi)
    # la porta della VM ha solo il gruppo di quarantena
    assert cloud_con_vm.gruppi_porta["porta-1"] == ["id-honey-quarantena"]
    assert ("gruppo_quarantena", "honey-quarantena", "p-service") \
        in cloud_con_vm.chiamate
    # i gruppi originali sono salvati
    [voce] = db.list_quarantine()
    assert voce["server_name"] == "web-01"
    assert json.loads(voce["original_groups"]) == ["sg-esca"]
    # allarme GRAVE di quarantena, oltre a quello dell'esca
    allarme = [a for a in db.list_alerts() if a["outcome"] == "quarantena"]
    assert len(allarme) == 1
    assert "VM web-01 isolata (gruppi originali: honey-esca)" \
        in allarme[0]["agent"]


def test_password_sbagliata_non_isola(eventi, cloud_con_vm, quarantena_attiva):
    attacco_dalla_vm(eventi, caso="esca_password_sbagliata")
    assert db.list_quarantine() == []
    assert cloud_con_vm.gruppi_porta["porta-1"] == ["sg-esca"]


def test_password_sbagliata_isola_se_richiesto(eventi, cloud_con_vm,
                                              quarantena_attiva):
    config.CONF.set_override("quarantine_on_failure", True)
    attacco_dalla_vm(eventi, caso="esca_password_sbagliata")
    assert len(db.list_quarantine()) == 1


def test_ip_fuori_dal_cloud_nessuna_quarantena(eventi, cloud_con_vm,
                                              quarantena_attiva):
    # Kali: l'IP non e' di nessuna VM, resta solo l'allarme dell'esca
    attacco_dalla_vm(eventi, ip="192.168.206.129")
    assert db.list_quarantine() == []
    assert [a["outcome"] for a in db.list_alerts()] == ["success"]


def test_vm_gia_in_quarantena_non_si_ripete(eventi, cloud_con_vm,
                                           quarantena_attiva):
    attacco_dalla_vm(eventi, n=1)
    attacco_dalla_vm(eventi, n=2)
    assert len(db.list_quarantine()) == 1
    assert len([a for a in db.list_alerts()
                if a["outcome"] == "quarantena"]) == 1


def test_quarantena_spenta(eventi, cloud_con_vm):
    attacco_dalla_vm(eventi)
    assert db.list_quarantine() == []


def test_errore_di_neutron_non_lascia_voci_false(eventi, cloud_con_vm,
                                                quarantena_attiva):
    cloud_con_vm.porta_rotta = True
    attacco_dalla_vm(eventi)
    # la VM non e' stata isolata: nessuna quarantena registrata,
    # ma l'allarme dell'esca resta e il watcher continua
    assert db.list_quarantine() == []
    assert [a["outcome"] for a in db.list_alerts()] == ["success"]


def test_rilascio(eventi, cloud_con_vm, quarantena_attiva):
    attacco_dalla_vm(eventi)
    assert quarantena.rilascia("web-01", cloud_con_vm) == "web-01"
    assert cloud_con_vm.gruppi_porta["porta-1"] == ["sg-esca"]
    assert db.list_quarantine() == []
    # lo storico resta
    assert db.list_quarantine(only_active=False)[0]["released_at"]


def test_rilascio_per_ip(eventi, cloud_con_vm, quarantena_attiva):
    attacco_dalla_vm(eventi)
    quarantena.rilascia(FIP, cloud_con_vm)
    assert db.list_quarantine() == []


def test_rilascio_di_una_vm_non_in_quarantena(cloud_finto):
    with pytest.raises(ValueError):
        quarantena.rilascia("web-02", cloud_finto)


def test_comandi_quarantine_list_e_release(eventi, cloud_con_vm,
                                          quarantena_attiva, capsys):
    attacco_dalla_vm(eventi)
    assert manager.main(["honey-stack", "quarantine-list"]) == 0
    assert "web-01 %s svc_deploy" % FIP in capsys.readouterr().out
    assert manager.main(["honey-stack", "release", "web-01"]) == 0
    assert "VM rilasciata" in capsys.readouterr().out
    assert manager.main(["honey-stack", "release", "web-01"]) == 1


class _Oggetto:
    def __init__(self, **campi):
        self.__dict__.update(campi)


class _RetePorte:
    """Risposte di Neutron per porta_da_ip e gruppo_quarantena."""

    def __init__(self):
        self.porta = _Oggetto(id="porta-1", device_id="vm-1",
                              device_owner="compute:nova",
                              project_id="p-service",
                              security_group_ids=["sg-esca"])
        self.cancellate = []

    def ips(self, floating_ip_address):
        if floating_ip_address == FIP:
            return [_Oggetto(port_id="porta-1")]
        return []

    def get_port(self, port_id):
        return self.porta

    def ports(self, fixed_ips):
        if fixed_ips == ["ip_address=10.0.0.3"]:
            return [self.porta]
        return []

    def get_security_group(self, gruppo):
        return _Oggetto(name="honey-esca")

    def find_security_group(self, nome, project_id):
        return None

    def create_security_group(self, **parametri):
        self.creato = parametri
        return _Oggetto(id="sg-q")

    def security_group_rules(self, security_group_id):
        return [_Oggetto(id="uscita-v4"), _Oggetto(id="uscita-v6")]

    def delete_security_group_rule(self, regola):
        self.cancellate.append(regola)


def test_porta_dal_floating_ip_e_dall_ip_fisso():
    rete = _RetePorte()
    c = cloud.Cloud(conn=_Oggetto(network=rete))
    atteso = {"port_id": "porta-1", "server_id": "vm-1",
              "project_id": "p-service", "gruppi": ["sg-esca"],
              "nomi_gruppi": ["honey-esca"]}
    assert c.porta_da_ip(FIP) == atteso
    assert c.porta_da_ip("10.0.0.3") == atteso
    assert c.porta_da_ip("192.168.206.129") is None


def test_gruppo_di_quarantena_senza_regole():
    rete = _RetePorte()
    c = cloud.Cloud(conn=_Oggetto(network=rete))
    assert c.gruppo_quarantena("honey-quarantena", "p-service") == "sg-q"
    assert rete.creato["project_id"] == "p-service"
    # tolte le regole di uscita che Neutron aggiunge da solo
    assert rete.cancellate == ["uscita-v4", "uscita-v6"]
