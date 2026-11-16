"""Controlli sui file "enabled" copiati in Horizon."""
import collections
import unittest

from openstack_dashboard.utils import settings as settings_utils

import honeystack_dashboard.enabled


class FileEnabled(unittest.TestCase):

    def configurazioni(self):
        return [c for _, c in settings_utils.import_dashboard_config(
            [honeystack_dashboard.enabled])]

    def test_app_aggiunta_una_sola_volta(self):
        # Horizon non toglie i doppioni: Django si fermerebbe con
        # "Application labels aren't unique"
        app = collections.Counter(
            a for c in self.configurazioni()
            for a in c.get("ADD_INSTALLED_APPS", []))
        self.assertEqual(app, {"honeystack_dashboard": 1})

    def test_gruppo_e_tre_pannelli_in_admin(self):
        pannelli = [c["PANEL"] for c in self.configurazioni() if "PANEL" in c]
        self.assertEqual(sorted(pannelli),
                         ["alerts", "honeytokens", "quarantines"])
        for c in self.configurazioni():
            self.assertEqual(c.get("PANEL_DASHBOARD",
                                   c.get("PANEL_GROUP_DASHBOARD")), "admin")
