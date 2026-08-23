from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("events/<int:event_id>/pledges/", views.pledges_view, name="pledges"),
    path("events/<int:event_id>/pledges/remind/", views.pledges_view, name="pledge_remind"),
    path("payments/", views.payments_view, name="payments"),
    path("webhook/palmpesa/", views.webhook_palmpesa, name="webhook_palmpesa"),
]
