from django import template

register = template.Library()


@register.filter
def dels_grups_de(feedbacks, usuari):
    if not usuari.is_authenticated:
        return feedbacks.none()
    if usuari.is_superuser or usuari.es_profe:
        return feedbacks.all()
    equips = usuari.equips.filter(membres=usuari)
    return feedbacks.filter(equip__in=equips)


@register.filter
def compte_dels_grups_de(feedbacks, usuari):
    return dels_grups_de(feedbacks, usuari).count()


@register.filter
def nom_estat(estat):
    """Nom visible d'un estat del tauler Kanban."""
    from scrum.kanban import NOMS_ESTAT

    return NOMS_ESTAT.get(estat, estat)


@register.filter
def nom_persona(usuari):
    if not usuari:
        return "—"
    return usuari.nom_complert or usuari.email


@register.filter
def inicials(usuari):
    """Dues lletres per a l'avatar d'una persona."""
    if not usuari:
        return "?"
    nom = usuari.nom_complert or usuari.email or "?"
    parts = nom.replace("@", " ").split()
    lletres = (parts[0][:1] + (parts[1][:1] if len(parts) > 1 else parts[0][1:2]))
    return lletres.upper()
