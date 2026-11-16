import horizon


class Pannello(horizon.Panel):
    name = "Honeytoken"
    slug = "honeytokens"
    # visibile solo se il servizio di Honey-Stack e' nel catalogo
    permissions = ("openstack.services.deception",)
