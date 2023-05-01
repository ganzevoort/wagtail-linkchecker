from django.urls import include, path
from django import urls as urlresolvers
from django.utils.translation import gettext_lazy as _

from wagtail.admin.menu import MenuItem
from wagtail import hooks

from . import urls


@hooks.register('register_admin_urls')
def register_admin_urls():
    return [
        path('link-checker/', include(urls)),
    ]


@hooks.register('register_settings_menu_item')
def register_menu_settings():
    return MenuItem(
        _('Link Checker'),
        urlresolvers.reverse('wagtaillinkchecker'),
        classnames='icon icon-link',
        order=300
    )
