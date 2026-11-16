from horizon import exceptions
from horizon import tables

from honeystack_dashboard import api
from honeystack_dashboard.quarantines import tables as tabelle


class IndexView(tables.DataTableView):
    table_class = tabelle.TabellaQuarantene
    page_title = "Quarantene"

    def get_data(self):
        try:
            return api.quarantene(self.request)
        except Exception:
            exceptions.handle(self.request,
                              "Impossibile leggere le quarantene.")
            return []
