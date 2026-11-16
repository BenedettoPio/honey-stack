
from horizon import exceptions
from horizon import forms
from horizon import messages

from honeystack_dashboard import api


class CreaEsca(forms.SelfHandlingForm):
    # stesse regole delle API: il nome diventa un utente di Keystone
    name = forms.RegexField(
        label="Nome", max_length=64, regex=r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*$",
        help_text="Nome credibile per l'utente esca, es. svc_backup",
        error_messages={"invalid": "Usa solo lettere, cifre e _ . -"})
    location = forms.CharField(
        label="Luogo dell'esca", max_length=255, required=False,
        help_text="Dove verranno lasciati i file, es. repository Git interno")

    def handle(self, request, data):
        try:
            esca = api.crea_esca(request, data["name"], data["location"])
        except api.Errore as e:
            self.api_error(str(e))
            return False
        except Exception:
            exceptions.handle(request, ignore=True)
            self.api_error("Impossibile creare il honeytoken.")
            return False
        messages.success(request, "Honeytoken %s creato: scarica i file "
                                  "esca dalla tabella." % esca.name)
        return esca
