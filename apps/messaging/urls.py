from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
    path("events/<int:event_id>/messages/", views.messages_view, name="messages"),
    path("events/<int:event_id>/cards/", views.cards_view, name="cards"),
]
