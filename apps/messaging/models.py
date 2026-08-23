from django.db import models

from apps.accounts.models import User
from apps.events.models import Event, Guest


class MessageTemplate(models.Model):
    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    name = models.CharField(max_length=120)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.SMS)
    subject = models.CharField(max_length=190, blank=True, null=True)
    body = models.TextField()
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class MessageLog(models.Model):
    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    event = models.ForeignKey(Event, on_delete=models.SET_NULL, blank=True, null=True, related_name="message_logs")
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, blank=True, null=True, related_name="message_logs")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    recipient = models.CharField(max_length=50)
    message = models.TextField()
    provider = models.CharField(max_length=80, blank=True, null=True)
    provider_message_id = models.CharField(max_length=190, blank=True, null=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    response_json = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["event"], name="idx_messages_event"),
            models.Index(fields=["status"], name="idx_messages_status"),
        ]

    def __str__(self):
        return f"{self.channel} → {self.recipient}"


class WhatsAppCard(models.Model):
    class Style(models.TextChoices):
        CLASSIC = "classic", "Classic"
        MINIMAL = "minimal", "Minimal"
        ROYAL = "royal", "Royal"
        MODERN = "modern", "Modern"
        CUSTOM = "custom", "Custom"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="cards")
    name = models.CharField(max_length=120)
    style = models.CharField(max_length=50, choices=Style.choices, default=Style.CLASSIC)
    headline = models.CharField(max_length=190, blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    background_url = models.CharField(max_length=255, blank=True, null=True)
    primary_color = models.CharField(max_length=20, default="#1C3A2E")
    accent_color = models.CharField(max_length=20, default="#FFFDD0")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} — {self.event.title}"


class NotificationQueue(models.Model):
    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    channel = models.CharField(max_length=10, choices=Channel.choices)
    recipient = models.CharField(max_length=50)
    message = models.TextField()
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, blank=True, null=True)
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, blank=True, null=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    last_error = models.CharField(max_length=500, blank=True, null=True)
    next_attempt_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="idx_queue_status"),
        ]

    def __str__(self):
        return f"{self.channel} → {self.recipient} [{self.status}]"
