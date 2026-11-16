from django.utils.html import format_html

from horizon import tables

COLORI = {"GRAVE": "danger", "ATTENZIONE": "warning"}


def gravita(allarme):
    return format_html('<span class="label label-{}">{}</span>',
                       COLORI.get(allarme.gravita, "default"),
                       allarme.gravita or allarme.outcome)


def orario(allarme):
    return allarme.event_time[:19].replace("T", " ")


class TabellaAllarmi(tables.DataTable):
    gravita = tables.Column(gravita, verbose_name="Gravità")
    event_time = tables.Column(orario, verbose_name="Orario (UTC)")
    name = tables.Column("name", verbose_name="Honeytoken")
    luogo = tables.Column("luogo", verbose_name="Luogo dell'esca")
    outcome = tables.Column("outcome", verbose_name="Evento")
    source_ip = tables.Column("source_ip", verbose_name="IP sorgente",
                              empty_value="-")
    agent = tables.Column("agent", verbose_name="Strumento / dettaglio")

    class Meta:
        name = "allarmi"
        verbose_name = "Allarmi"
