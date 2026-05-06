from django import template

from permission.services import has_permission


register = template.Library()


@register.simple_tag
def can_menu(user, menu_code, action='view'):
    return has_permission(user, menu_code, action)
