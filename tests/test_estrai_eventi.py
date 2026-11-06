"""Test dello script che estrae gli eventi CADF dal journal."""
import importlib.util
import json
import pathlib

SCRIPT = pathlib.Path(__file__).parent.parent / "tools" / "estrai_eventi.py"
spec = importlib.util.spec_from_file_location("estrai_eventi", SCRIPT)
estrai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(estrai)


def riga_journal(evento):
    """Riga come la scrive oslo.log con debug = True."""
    return ("2026-11-06 11:36:31.600 4321 DEBUG honeystack.watcher [-] "
            "Evento CADF: %s _gestisci /opt/stack/honey-stack/honeystack/"
            "watcher.py:46\n" % json.dumps(evento))


def test_riconosce_i_quattro_casi(eventi, tmp_path, monkeypatch, capsys):
    righe = ["riga qualsiasi del journal\n"]
    righe += [riga_journal(e) for e in eventi.values()]
    monkeypatch.setattr("sys.stdin", righe)
    destinazione = tmp_path / "eventi.json"
    assert estrai.main(["estrai", "svc_backup", str(destinazione)]) == 0
    assert json.loads(destinazione.read_text()) == eventi


def test_segnala_i_casi_mancanti(eventi, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin",
                        [riga_journal(eventi["admin_reale"])])
    assert estrai.main(["estrai", "svc_backup",
                        str(tmp_path / "eventi.json")]) == 1
    assert "Mancano" in capsys.readouterr().out
