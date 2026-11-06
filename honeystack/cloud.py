"""Honey-Stack - Accesso a OpenStack.

Tutte le chiamate a Keystone passano da qui: il resto del codice non
dipende dai dettagli di openstacksdk e nei test la classe Cloud si
sostituisce con una finta che registra le chiamate.
"""
import openstack

from honeystack import config


class Cloud:
    """Operazioni su Keystone con l'utente di servizio di Honey-Stack."""

    def __init__(self, conn=None):
        self._conn = conn

    @property
    def conn(self):
        # la connessione si apre solo quando serve davvero
        if self._conn is None:
            self._conn = config.connessione()
        return self._conn

    def auth_url(self):
        """Indirizzo di Keystone da scrivere nei file esca."""
        return self.conn.config.auth.get("auth_url") or config.auth_url()

    def utente_esiste(self, nome):
        return self.conn.identity.find_user(nome) is not None

    def progetto_esche(self, nome):
        """Progetto isolato delle esche, creato se manca: (id, nome)."""
        progetto = self.conn.identity.find_project(nome)
        if progetto is None:
            progetto = self.conn.identity.create_project(
                name=nome, domain_id="default",
                description="Progetto isolato per honeytoken")
        return progetto.id, progetto.name

    def crea_utente(self, nome, password, progetto_id):
        """Crea l'utente esca, senza ruoli; restituisce il suo ID."""
        utente = self.conn.identity.create_user(
            name=nome, password=password, domain_id="default",
            default_project_id=progetto_id)
        return utente.id

    def elimina_utente(self, user_id):
        self.conn.identity.delete_user(user_id, ignore_missing=True)

    def login_admin(self, utente, password):
        """Vero se l'utente si autentica e ha il ruolo admin."""
        try:
            conn = openstack.connect(
                auth_url=config.auth_url(), username=utente,
                password=password, project_name="admin",
                user_domain_name="Default", project_domain_name="Default",
                load_yaml_config=False, load_envvars=False)
            accesso = conn.session.auth.get_access(conn.session)
        except Exception:
            return False
        return "admin" in accesso.role_names

    def token_admin(self, token):
        """Vero se il token Keystone e' valido e ha il ruolo admin."""
        if not token:
            return False
        try:
            risposta = self.conn.session.get(
                config.auth_url() + "/v3/auth/tokens",
                headers={"X-Subject-Token": token}, raise_exc=False)
        except Exception:
            return False
        if risposta.status_code != 200:
            return False
        ruoli = risposta.json()["token"].get("roles", [])
        return any(r["name"] == "admin" for r in ruoli)
