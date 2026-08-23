from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("events/", views.event_list, name="list"),
    path("events/create/", views.event_create, name="create"),
    path("events/<int:event_id>/", views.event_detail, name="detail"),
    path("events/<int:event_id>/guests/", views.guests_view, name="guests"),
    path("i/<str:token>/", views.public_event, name="public_event"),
    path("rsvp/<str:token>/", views.rsvp_view, name="rsvp"),
    path("rsvp/<str:token>/submit/", views.rsvp_submit, name="rsvp_submit"),
]
