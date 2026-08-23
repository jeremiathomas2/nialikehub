import secrets
from django.db import models

from apps.accounts.models import User


def _token():
    return secrets.token_hex(24)


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        CLOSED = "closed", "Closed"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="events", db_column="user_id")
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=190, unique=True)
    event_type = models.CharField(max_length=80, default="General")
    description = models.TextField(blank=True, null=True)
    event_date = models.DateField()
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    venue = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    cover_image = models.CharField(max_length=255, blank=True, null=True)
    primary_color = models.CharField(max_length=20, default="#1C3A2E")
    accent_color = models.CharField(max_length=20, default="#FFFDD0")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    public_token = models.CharField(max_length=48, unique=True, default=_token)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"], name="idx_events_owner"),
            models.Index(fields=["status"], name="idx_events_status"),
        ]

    def __str__(self):
        return self.title


class Guest(models.Model):
    class InvitationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        VIEWED = "viewed", "Viewed"
        RSVP_YES = "rsvp_yes", "RSVP Yes"
        RSVP_NO = "rsvp_no", "RSVP No"
        CHECKED_IN = "checked_in", "Checked In"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="guests")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(max_length=190, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    seats = models.IntegerField(default=1)
    invitation_status = models.CharField(
        max_length=15, choices=InvitationStatus.choices, default=InvitationStatus.PENDING
    )
    rsvp_token = models.CharField(max_length=48, unique=True, default=_token)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["event"], name="idx_guests_event"),
            models.Index(fields=["phone"], name="idx_guests_phone"),
            models.Index(fields=["invitation_status"], name="idx_guests_status"),
        ]

    def __str__(self):
        return f"{self.name} ({self.event.title})"
