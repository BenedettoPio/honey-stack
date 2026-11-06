"""Test del gestore degli honeytoken (manager.py), con OpenStack finto."""
import os
import stat

import pytest

from honeystack import db, manager


def test_password_casuale():
    password = manager.genera_password()
    assert len(password) == 20
    assert password.isalnum()
    assert password != manager.genera_password()


def test_crea_honeytoken(cloud_finto):
    cartella = manager.create_honeytoken("svc_backup", "Kali ~/Downloads")
    # utente creato nel progetto delle esche, senza altre operazioni
    assert ("progetto_esche", "infra-ops") in cloud_finto.chiamate
    assert ("crea_utente", "svc_backup", "id-progetto-infra-ops") \
        in cloud_finto.chiamate
    # registrato nel database con il suo luogo
    esca = db.get_active_honeytoken("id-svc_backup")
    assert esca["luogo"] == "Kali ~/Downloads"
    assert esca["project_id"] == "id-progetto-infra-ops"
    # file esca con le credenziali giuste e permessi ristretti
    password = cloud_finto.password["svc_backup"]
    clouds = open(os.path.join(cartella, "clouds.yaml")).read()
    openrc = open(os.path.join(cartella, "openrc")).read()
    for testo in (clouds, openrc):
        assert "svc_backup" in testo
        assert password in testo
        assert "infra-ops" in testo
        assert "http://keystone.test/identity" in testo
    assert stat.S_IMODE(os.stat(cartella).st_mode) == 0o700
    for file in ("clouds.yaml", "openrc"):
        modo = os.stat(os.path.join(cartella, file)).st_mode
        assert stat.S_IMODE(modo) == 0o600


def test_non_crea_un_utente_che_esiste_gia(cloud_finto):
    with pytest.raises(ValueError):
        manager.create_honeytoken("admin")
    assert not any(c[0] == "crea_utente" for c in cloud_finto.chiamate)


def test_elimina_honeytoken(cloud_finto):
    manager.create_honeytoken("svc_backup")
    manager.delete_honeytoken("svc_backup")
    assert ("elimina_utente", "id-svc_backup") in cloud_finto.chiamate
    assert db.get_active_honeytoken("id-svc_backup") is None


def test_non_elimina_un_utente_vero(cloud_finto):
    # admin non e' registrato come esca: nessuna chiamata a Keystone
    with pytest.raises(ValueError):
        manager.delete_honeytoken("admin")
    assert cloud_finto.chiamate == []
