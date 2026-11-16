from django.utils.translation import ngettext_lazy

from horizon import tables

from honeystack_dashboard import api


class Rilascia(tables.BatchAction):
    name = "release"
    icon = "unlock"
    help_text = ("Alla VM vengono rimessi i gruppi di sicurezza che aveva "
                 "prima della quarantena.")

    @staticmethod
    def action_present(count):
        return ngettext_lazy("Rilascia VM", "Rilascia VM", count)

    @staticmethod
    def action_past(count):
        return ngettext_lazy("VM rilasciata", "VM rilasciate", count)

    def action(self, request, obj_id):
        api.rilascia(request, obj_id)


def dal(voce):
    return voce.started_at[:19].replace("T", " ")


class TabellaQuarantene(tables.DataTable):
    server_name = tables.Column("server_name", verbose_name="VM")
    source_ip = tables.Column("source_ip", verbose_name="IP")
    honeytoken = tables.Column("honeytoken", verbose_name="Esca usata")
    started_at = tables.Column(dal, verbose_name="In quarantena dal (UTC)")

    class Meta:
        name = "quarantene"
        verbose_name = "VM in quarantena"
        table_actions = (Rilascia,)
        row_actions = (Rilascia,)
