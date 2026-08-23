from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("favicon.ico", RedirectView.as_view(url="/static/img/favicon/favicon.ico", permanent=True)),
    path("", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
    path("", include("apps.events.urls")),
    path("", include("apps.finance.urls")),
    path("", include("apps.messaging.urls")),
]
