"""Web addresses: /admin for the admin portal, /api/... for the phone app. Everything else is the app itself."""
from django.urls import include, path
from django.views.generic import RedirectView

from kitchen.admin import admin_site

urlpatterns = [
    path('admin/', admin_site.urls),
    path('api/', include('kitchen.urls')),
    # Browsers ask for /favicon.ico on every page, including the admin portal.
    path('favicon.ico', RedirectView.as_view(url='/icon.svg', permanent=True)),
]
