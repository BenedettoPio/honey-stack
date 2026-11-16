import horizon


class Pannello(horizon.Panel):
    name = "Quarantene"
    slug = "quarantines"
    # visibile solo se il servizio di Honey-Stack e' nel catalogo
    permissions = ("openstack.services.deception",)
