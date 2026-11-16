from django.urls import reverse
from django.utils.translation import ngettext_lazy

from horizon import tables

from honeystack_dashboard import api


class CreaEsca(tables.LinkAction):
    name = "create"
    verbose_name = "Crea honeytoken"
    url = "horizon:admin:honeytokens:create"
    classes = ("ajax-modal",)
    icon = "plus"


class ScaricaFile(tables.LinkAction):
    file = None
    ajax = False
    icon = "download"

    def get_link_url(self, datum):
        return reverse("horizon:admin:honeytokens:download",
                       args=[datum.name, self.file])


class ScaricaClouds(ScaricaFile):
    name = "clouds_yaml"
    verbose_name = "Scarica clouds.yaml"
    file = "clouds.yaml"


class ScaricaOpenrc(ScaricaFile):
    name = "openrc"
    verbose_name = "Scarica openrc"
    file = "openrc"


class EliminaEsca(tables.DeleteAction):
    help_text = ("L'utente esca viene cancellato da Keystone e i file "
                 "esca smettono di funzionare.")

    @staticmethod
    def action_present(count):
        return ngettext_lazy("Elimina honeytoken", "Elimina honeytoken",
                             count)

    @staticmethod
    def action_past(count):
        return ngettext_lazy("Honeytoken eliminato", "Honeytoken eliminati",
                             count)

    def delete(self, request, obj_id):
        api.elimina_esca(request, obj_id)


def creato(esca):
    return esca.created_at[:19].replace("T", " ")


class TabellaEsche(tables.DataTable):
    name = tables.Column("name", verbose_name="Nome")
    luogo = tables.Column("luogo", verbose_name="Luogo dell'esca",
                          empty_value="-")
    created_at = tables.Column(creato, verbose_name="Creato (UTC)")

    class Meta:
        name = "esche"
        verbose_name = "Honeytoken attivi"
        table_actions = (CreaEsca, EliminaEsca)
        row_actions = (ScaricaClouds, ScaricaOpenrc, EliminaEsca)
