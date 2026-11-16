from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views import generic

from horizon import exceptions
from horizon import forms
from horizon import tables

from honeystack_dashboard import api
from honeystack_dashboard.honeytokens import forms as moduli
from honeystack_dashboard.honeytokens import tables as tabelle

INDICE = reverse_lazy("horizon:admin:honeytokens:index")


class IndexView(tables.DataTableView):
    table_class = tabelle.TabellaEsche
    page_title = "Honeytoken"

    def get_data(self):
        try:
            return api.esche(self.request)
        except Exception:
            exceptions.handle(self.request,
                              "Impossibile leggere i honeytoken.")
            return []


class CreateView(forms.ModalFormView):
    form_class = moduli.CreaEsca
    template_name = "admin/honeytokens/create.html"
    modal_id = "crea_honeytoken_modal"
    submit_url = reverse_lazy("horizon:admin:honeytokens:create")
    success_url = INDICE
    submit_label = page_title = "Crea honeytoken"


class DownloadView(generic.View):
    """Inoltra il file esca preso dalle API come download."""

    def get(self, request, nome, file):
        try:
            contenuto = api.file_esca(request, nome, file)
        except Exception:
            exceptions.handle(request, "Impossibile scaricare %s." % file,
                              redirect=INDICE)
        risposta = HttpResponse(contenuto, content_type="text/plain")
        risposta["Content-Disposition"] = 'attachment; filename="%s"' % file
        return risposta
