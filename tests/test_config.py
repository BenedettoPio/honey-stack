"""Test della configurazione (config.py, oslo.config)."""
from honeystack import config


def test_valori_dal_file():
    assert config.get("decoy_project") == "infra-ops"
    assert config.get("dashboard_port") == 6060


def test_porta_e_un_numero():
    assert isinstance(config.get("dashboard_port"), int)


def test_senza_utente_di_servizio_usa_l_ambiente():
    assert not config.ha_utente_di_servizio()
    assert config.auth_url() == "http://keystone.test/identity"


def test_password_segreta_e_opzioni_per_il_generatore():
    gruppi = dict(config.list_opts())
    assert set(gruppi) == {"DEFAULT", "service_user"}
    password = [o for o in gruppi["service_user"] if o.name == "password"]
    assert password[0].secret
    for opzioni in gruppi.values():
        assert all(o.help for o in opzioni)
