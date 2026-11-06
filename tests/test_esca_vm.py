"""Test dell'esca dentro una VM (manager.create_honeytoken_vm)."""
import os
import subprocess

import pytest

from honeystack import db, manager


def test_esca_creata_dentro_una_nuova_vm(cloud_finto):
    dati = manager.create_honeytoken_vm("svc_deploy", "web-01")
    # VM con immagine CirrOS, valori di configurazione e gruppo SSH
    assert ("crea_vm", "web-01", "cirros-0.6.3-x86_64-disk", "m1.tiny",
            "private", "honey-esca", "public") in cloud_finto.chiamate
    assert dati["floating"] == "172.24.4.115"
    # nel database il luogo dice in quale VM si trova l'esca
    esca = db.get_active_honeytoken("id-svc_deploy")
    assert esca["luogo"] == ("VM web-01 (10.0.0.20, 172.24.4.115) "
                             "~cirros/.config/openstack/clouds.yaml")


def test_lo_script_contiene_le_credenziali_dell_esca(cloud_finto):
    manager.create_honeytoken_vm("svc_deploy", "web-01")
    script = cloud_finto.script["web-01"]
    password = cloud_finto.password["svc_deploy"]
    assert script.startswith("#!/bin/sh\n")
    assert "username: svc_deploy" in script
    assert "password: " + password in script
    assert "project_name: infra-ops" in script
    assert "/home/cirros/.config/openstack/clouds.yaml" in script


def test_lo_script_scrive_il_file_esca(cloud_finto, tmp_path):
    # si esegue lo script vero, con /home spostata in una cartella di prova
    manager.create_honeytoken_vm("svc_deploy", "web-01")
    script = cloud_finto.script["web-01"].replace("/home/", "%s/" % tmp_path)
    script = "\n".join(r for r in script.splitlines()
                       if not r.startswith("chown"))
    subprocess.run(["sh", "-c", script], check=True)
    scritto = tmp_path / "cirros/.config/openstack/clouds.yaml"
    locale = os.path.join(manager.DECOY_DIR, "svc_deploy", "clouds.yaml")
    assert scritto.read_text() == open(locale).read()
    assert oct(scritto.stat().st_mode)[-3:] == "600"


def test_se_la_vm_non_parte_l_esca_viene_cancellata(cloud_finto):
    cloud_finto.vm_rotta = True
    with pytest.raises(ValueError, match="VM web-01 non creata"):
        manager.create_honeytoken_vm("svc_deploy", "web-01")
    assert ("elimina_utente", "id-svc_deploy") in cloud_finto.chiamate
    assert db.list_honeytokens() == []


def test_nome_esca_gia_usato(cloud_finto):
    with pytest.raises(ValueError):
        manager.create_honeytoken_vm("admin", "web-01")
    assert not any(c[0] == "crea_vm" for c in cloud_finto.chiamate)


def test_comando_create_vm(cloud_finto, capsys):
    assert manager.main(["honey-stack", "create-vm", "svc_deploy",
                         "web-01"]) == 0
    uscita = capsys.readouterr().out
    assert "Floating IP: 172.24.4.115" in uscita
    assert "VM web-01" in uscita


class _Oggetto:
    def __init__(self, **campi):
        self.__dict__.update(campi)


class _ConnFinta:
    """Risposte nel formato di Nova e Neutron, per cloud.Cloud."""

    current_project_id = "p-service"

    def __init__(self):
        self.creati = []
        self.compute = _Oggetto(get_server=lambda i: _Oggetto(
            id=i, addresses={"private": [
                {"addr": "fd19::5", "version": 6,
                 "OS-EXT-IPS:type": "fixed"},
                {"addr": "10.0.0.20", "version": 4,
                 "OS-EXT-IPS:type": "fixed"},
                {"addr": "172.24.4.115", "version": 4,
                 "OS-EXT-IPS:type": "floating"}]}))
        self.network = _Oggetto(
            find_security_group=lambda nome, project_id: None,
            create_security_group=self._crea_gruppo,
            create_security_group_rule=lambda **r: self.creati.append(r))

    def _crea_gruppo(self, name, description):
        self.creati.append(name)
        return _Oggetto(id="sg1", name=name)

    def create_server(self, **parametri):
        self.parametri = parametri
        return _Oggetto(id="vm1")


def test_cloud_crea_vm_e_legge_gli_indirizzi():
    from honeystack import cloud
    conn = _ConnFinta()
    c = cloud.Cloud(conn=conn)
    assert c.crea_vm("web-01", "#!/bin/sh", "cirros", "m1.tiny", "private",
                     "honey-esca", "public") == ("vm1", "10.0.0.20",
                                                 "172.24.4.115")
    assert conn.parametri["userdata"] == "#!/bin/sh"
    assert conn.parametri["ip_pool"] == "public"
    assert conn.parametri["wait"] is True


def test_cloud_crea_il_gruppo_ssh_se_manca():
    from honeystack import cloud
    conn = _ConnFinta()
    assert cloud.Cloud(conn=conn).gruppo_ssh("honey-esca") == "honey-esca"
    regole = [r for r in conn.creati if isinstance(r, dict)]
    assert {r["protocol"] for r in regole} == {"icmp", "tcp"}
    assert all(r["direction"] == "ingress" for r in regole)
