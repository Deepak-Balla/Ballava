"""Web addresses: /admin for the admin portal, /api/... for the phone app. Everything else is the app itself."""
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from kitchen import api
from kitchen.admin import admin_site

urlpatterns = [
    path('admin/', admin_site.urls),
    path('api/', include('kitchen.urls')),
    # Short voting links, as shared on WhatsApp: /v/<ballot> or /v/<ballot>/<meal>-<dish>
    path('v/<slug:group>', api.vote_link),
    re_path(r'^v/(?P<group>[\w-]+)/(?P<choice>\d+-\d+)$', api.vote_link),
    # Browsers ask for /favicon.ico on every page, including the admin portal.
    path('favicon.ico', RedirectView.as_view(url='/icon.svg', permanent=True)),
]
