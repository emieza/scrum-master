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
