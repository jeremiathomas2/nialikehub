from django.db import models

from apps.events.models import Event, Guest


class Pledge(models.Model):
    class Status(models.TextChoices):
        PROMISED = "promised", "Promised"
        PARTIAL = "partial", "Partial"
        PAID = "paid", "Paid"
        DEFAULTED = "defaulted", "Defaulted"
        CANCELLED = "cancelled", "Cancelled"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="pledges")
    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name="pledges")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    due_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROMISED)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["event"], name="idx_pledges_event"),
            models.Index(fields=["guest"], name="idx_pledges_guest"),
            models.Index(fields=["status"], name="idx_pledges_status"),
        ]

    def __str__(self):
        return f"{self.guest.name} — {self.amount} TZS"

    @property
    def balance(self):
        return max(self.amount - self.paid_amount, 0)


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="payments")
    pledge = models.ForeignKey(Pledge, on_delete=models.SET_NULL, blank=True, null=True, related_name="payments")
    guest = models.ForeignKey(Guest, on_delete=models.SET_NULL, blank=True, null=True, related_name="payments")
    provider = models.CharField(max_length=50, default="manual")
    reference = models.CharField(max_length=120, unique=True)
    provider_reference = models.CharField(max_length=190, blank=True, null=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default="TZS")
    phone = models.CharField(max_length=30, blank=True, null=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    raw_response = models.TextField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["event"], name="idx_payments_event"),
            models.Index(fields=["status"], name="idx_payments_status"),
            models.Index(fields=["reference"], name="idx_payments_reference"),
        ]

    def __str__(self):
        return f"{self.reference} — {self.amount} {self.currency}"
