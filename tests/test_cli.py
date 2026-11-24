"""Test del comando honey-stack (cli.py): un client delle API REST.

Le richieste del comando arrivano all'app Flask vera (fixture cli_su_api),
che usa OpenStack finto: si prova tutto il percorso comando -> API.
"""
import os
import stat

from honeystack import cli, db


def test_il_comando_non_usa_database_ne_openstack():
    # e' solo un client: non importa i moduli del lato server
    for modulo in ("db", "cloud", "manager", "config", "quarantena"):
        assert modulo not in vars(cli)


def test_create_e_files(cli_su_api, cloud_finto, tmp_path, capsys):
    assert cli_su_api.main(["honey-stack", "create", "svc_backup",
                            "Kali ~/Downloads"]) == 0
    assert "Honeytoken creato: svc_backup" in capsys.readouterr().out
    # l'esca l'hanno creata le API, con il gestore lato server
    assert db.get_active_honeytoken("id-svc_backup")["luogo"] == \
        "Kali ~/Downloads"
    # i file esca si scaricano dalle API nella cartella scelta
    cartella = str(tmp_path / "esca")
    assert cli_su_api.main(["honey-stack", "files", "svc_backup",
                            cartella]) == 0
    password = cloud_finto.password["svc_backup"]
    for file in ("clouds.yaml", "openrc"):
        percorso = tmp_path / "esca" / file
        assert password in percorso.read_text()
        assert stat.S_IMODE(os.stat(percorso).st_mode) == 0o600


def test_create_di_un_nome_gia_usato(cli_su_api, capsys):
    assert cli_su_api.main(["honey-stack", "create", "admin"]) == 1
    assert "Errore: Esiste gia' un utente" in capsys.readouterr().out


def test_create_con_un_nome_non_valido(cli_su_api, cloud_finto, capsys):
    assert cli_su_api.main(["honey-stack", "create", "../etc"]) == 1
    assert "non valido" in capsys.readouterr().out
    assert cloud_finto.chiamate == []


def test_list_e_delete(cli_su_api, capsys):
    cli_su_api.main(["honey-stack", "create", "svc_backup"])
    capsys.readouterr()
    assert cli_su_api.main(["honey-stack", "list"]) == 0
    assert capsys.readouterr().out.startswith("svc_backup id-svc_backup")
    assert cli_su_api.main(["honey-stack", "delete", "svc_backup"]) == 0
    assert db.list_honeytokens() == []


def test_files_di_un_esca_che_non_esiste(cli_su_api, tmp_path, capsys):
    assert cli_su_api.main(["honey-stack", "files", "sconosciuta",
                            str(tmp_path / "x")]) == 1
    assert "Errore" in capsys.readouterr().out


def test_delete_di_un_utente_che_non_e_esca(cli_su_api, cloud_finto,
                                            capsys):
    assert cli_su_api.main(["honey-stack", "delete", "admin"]) == 1
    assert "non e' un honeytoken attivo" in capsys.readouterr().out
    assert cloud_finto.chiamate == []


def test_alerts(cli_su_api, capsys):
    db.save_alert(event_id="e1", user_id="u1", name="svc_backup",
                  outcome="success", source_ip="192.168.206.129",
                  agent="curl/8.18.0", event_time="2026-11-20T12:28:36")
    assert cli_su_api.main(["honey-stack", "alerts"]) == 0
    assert "GRAVE svc_backup success 192.168.206.129" in \
        capsys.readouterr().out


def test_api_non_raggiungibili(monkeypatch, capsys):
    # niente openrc o servizio deception assente: messaggio chiaro
    def sessione():
        raise RuntimeError("Missing value auth-url")
    monkeypatch.setattr(cli, "_sessione", sessione)
    assert cli.main(["honey-stack", "list"]) == 1
    assert "API di Honey-Stack non raggiungibili" in \
        capsys.readouterr().out


def test_comando_sconosciuto(capsys):
    assert cli.main(["honey-stack", "boh"]) == 1
    assert "Uso:" in capsys.readouterr().out
