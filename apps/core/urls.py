from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("gateway/", views.gateway_view, name="gateway"),
    path("audit/", views.audit_view, name="audit"),
]
