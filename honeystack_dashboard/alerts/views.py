from horizon import exceptions
from horizon import tables

from honeystack_dashboard import api
from honeystack_dashboard.alerts import tables as tabelle


class IndexView(tables.DataTableView):
    table_class = tabelle.TabellaAllarmi
    template_name = "admin/alerts/index.html"
    page_title = "Allarmi Honey-Stack"

    def get_data(self):
        try:
            return api.allarmi(self.request)
        except Exception:
            exceptions.handle(self.request,
                              "Impossibile leggere gli allarmi di Honey-Stack.")
            return []
