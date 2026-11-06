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

    def stato_utente(self, user_id):
        """'assente', 'disattivato' oppure 'attivo'."""
        utente = self.conn.identity.find_user(user_id)
        if utente is None:
            return "assente"
        return "attivo" if utente.is_enabled else "disattivato"

    def riattiva_utente(self, user_id):
        self.conn.identity.update_user(user_id, is_enabled=True)

    def ruoli_utente(self, user_id):
        """Ruoli assegnati direttamente all'utente, con il loro ambito."""
        ruoli = []
        for a in self.conn.identity.role_assignments(
                user_id=user_id, include_names=True):
            ruolo = a.role or {}
            for ambito, dati in (a.scope or {}).items():
                dati = dati if isinstance(dati, dict) else {}
                ruoli.append({
                    "ruolo_id": ruolo.get("id"),
                    "ruolo": ruolo.get("name", ruolo.get("id")),
                    "ambito": ambito,
                    "ambito_id": dati.get("id", "all"),
                    "ambito_nome": dati.get("name",
                                            dati.get("id", "all")),
                })
        return ruoli

    def rimuovi_ruolo(self, user_id, ruolo):
        identity = self.conn.identity
        if ruolo["ambito"] == "project":
            identity.unassign_project_role_from_user(
                ruolo["ambito_id"], user_id, ruolo["ruolo_id"])
        elif ruolo["ambito"] == "domain":
            identity.unassign_domain_role_from_user(
                ruolo["ambito_id"], user_id, ruolo["ruolo_id"])
        else:
            identity.unassign_system_role_from_user(
                user_id, ruolo["ruolo_id"], "all")

    def immagine_cirros(self):
        """Nome della prima immagine CirrOS disponibile."""
        for immagine in self.conn.image.images():
            if "cirros" in (immagine.name or "").lower():
                return immagine.name
        raise ValueError("Nessuna immagine CirrOS disponibile")

    def gruppo_ssh(self, nome):
        """Security group con ping e SSH in entrata, creato se manca."""
        rete = self.conn.network
        gruppo = rete.find_security_group(
            nome, project_id=self.conn.current_project_id)
        if gruppo is None:
            gruppo = rete.create_security_group(
                name=nome, description="VM con esca: ping e SSH")
            rete.create_security_group_rule(
                security_group_id=gruppo.id, direction="ingress",
                ethertype="IPv4", protocol="icmp")
            rete.create_security_group_rule(
                security_group_id=gruppo.id, direction="ingress",
                ethertype="IPv4", protocol="tcp",
                port_range_min=22, port_range_max=22)
        return gruppo.name

    def crea_vm(self, nome, script, immagine, flavor, rete, gruppo,
                pool):
        """Avvia una VM con lo script di avvio e aspetta che sia attiva.

        Restituisce (id, IP fisso, floating IP o None).
        """
        server = self.conn.create_server(
            name=nome, image=immagine, flavor=flavor, network=rete,
            security_groups=[gruppo], userdata=script, wait=True,
            timeout=600, auto_ip=bool(pool), ip_pool=pool or None)
        server = self.conn.compute.get_server(server.id)
        fisso = floating = None
        for indirizzi in (server.addresses or {}).values():
            for a in indirizzi:
                if a.get("version") != 4:
                    continue
                if a.get("OS-EXT-IPS:type") == "floating":
                    floating = a["addr"]
                else:
                    fisso = a["addr"]
        return server.id, fisso, floating

    def porta_da_ip(self, ip):
        """Porta Neutron della VM con quel floating IP o IP fisso.

        Restituisce un dizionario (porta, VM, progetto, gruppi) o None se
        l'indirizzo non appartiene a una VM del cloud.
        """
        rete = self.conn.network
        port_id = None
        for fip in rete.ips(floating_ip_address=ip):
            port_id = fip.port_id
        if port_id:
            porta = rete.get_port(port_id)
        else:
            porte = [p for p in rete.ports(fixed_ips=["ip_address=" + ip])
                     if (p.device_owner or "").startswith("compute:")]
            if not porte:
                return None
            porta = porte[0]
        if not (porta.device_owner or "").startswith("compute:"):
            return None
        gruppi = list(porta.security_group_ids or [])
        return {"port_id": porta.id, "server_id": porta.device_id,
                "project_id": porta.project_id, "gruppi": gruppi,
                "nomi_gruppi": [rete.get_security_group(g).name
                                for g in gruppi]}

    def nome_vm(self, server_id):
        return self.conn.compute.get_server(server_id).name

    def gruppo_quarantena(self, nome, project_id):
        """Security group senza regole (blocca tutto), creato se manca."""
        rete = self.conn.network
        gruppo = rete.find_security_group(nome, project_id=project_id)
        if gruppo is None:
            gruppo = rete.create_security_group(
                name=nome, project_id=project_id,
                description="Honey-Stack: VM in quarantena, nessun "
                            "traffico permesso")
            # Neutron aggiunge a ogni gruppo nuovo le regole che
            # permettono tutto il traffico in uscita: si tolgono
            for regola in rete.security_group_rules(
                    security_group_id=gruppo.id):
                rete.delete_security_group_rule(regola.id)
        return gruppo.id

    def imposta_gruppi(self, port_id, gruppi):
        self.conn.network.update_port(port_id, security_group_ids=gruppi)

    def gruppi_utente(self, user_id):
        return [{"id": g.id, "nome": g.name}
                for g in self.conn.identity.user_groups(user_id)]

    def rimuovi_da_gruppo(self, user_id, group_id):
        self.conn.identity.remove_user_from_group(user_id, group_id)

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
