# Gruppo "Honey-Stack" nella dashboard Admin di Horizon.
PANEL_GROUP = 'honeystack'
PANEL_GROUP_NAME = 'Honey-Stack'
PANEL_GROUP_DASHBOARD = 'admin'
# L'app Django va aggiunta una sola volta: Horizon non toglie i doppioni
# e Django si ferma se due app hanno lo stesso nome.
ADD_INSTALLED_APPS = ['honeystack_dashboard']
