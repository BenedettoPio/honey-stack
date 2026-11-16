import horizon


class Pannello(horizon.Panel):
    name = "Allarmi"
    slug = "alerts"
    # visibile solo se il servizio di Honey-Stack e' nel catalogo
    permissions = ("openstack.services.deception",)
