"""Impostazioni di Horizon per i test dei pannelli di Honey-Stack."""
from openstack_dashboard.test.settings import *  # noqa: F401,F403
from openstack_dashboard.test.settings import HORIZON_CONFIG, INSTALLED_APPS
from openstack_dashboard import enabled
from openstack_dashboard.utils import settings as settings_utils

import honeystack_dashboard.enabled

settings_utils.update_dashboards(
    [enabled, honeystack_dashboard.enabled], HORIZON_CONFIG, INSTALLED_APPS)
# la seconda chiamata ripete le app di Horizon gia' presenti; che le
# nostre compaiano una volta sola lo controlla test_enabled.py
INSTALLED_APPS = list(dict.fromkeys(INSTALLED_APPS))
