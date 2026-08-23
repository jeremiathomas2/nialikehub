from django.conf import settings
from django.db import models

from apps.accounts.models import User


class Setting(models.Model):
    setting_key = models.CharField(max_length=100, unique=True)
    setting_value = models.TextField(blank=True, null=True)
    is_secret = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.setting_key


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name="audit_logs")
    action = models.CharField(max_length=120)
    entity = models.CharField(max_length=120, blank=True, null=True)
    entity_id = models.IntegerField(blank=True, null=True)
    meta_json = models.TextField(blank=True, null=True)
    ip_address = models.CharField(max_length=64, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"], name="idx_audit_user"),
            models.Index(fields=["created_at"], name="idx_audit_created"),
        ]

    def __str__(self):
        return f"{self.action} by {self.user}"

    @property
    def meta(self):
        import json

        try:
            return json.loads(self.meta_json) if self.meta_json else {}
        except (ValueError, TypeError):
            return {}

    @property
    def actor_name(self):
        return self.user.name if self.user else "System"


DEFAULT_SETTINGS = {
    "brand_name": "Nialike",
    "default_primary_color": "#1C3A2E",
    "default_accent_color": "#FFFDD0",
    "footer_text": "Digital Invitations • Events • Pledges • Payments",
}


def get_setting(key, default=""):
    try:
        row = Setting.objects.get(setting_key=key)
        return row.setting_value if row.setting_value not in (None, "") else default
    except Setting.DoesNotExist:
        return DEFAULT_SETTINGS.get(key, default)


def set_setting(key, value, is_secret=False):
    Setting.objects.update_or_create(
        setting_key=key,
        defaults={"setting_value": value, "is_secret": is_secret},
    )


def branding_context():
    """Branding values used across templates."""
    brand_name = get_setting("brand_name", "Nialike")
    return {
        "brand_name": brand_name,
        "app_name": brand_name,
        "currency": get_setting("currency", "TZS"),
        "default_primary_color": get_setting("default_primary_color", "#1C3A2E"),
        "default_accent_color": get_setting("default_accent_color", "#FFFDD0"),
        "footer_text": get_setting("footer_text", ""),
        "app_url": settings.APP_URL if hasattr(settings, "APP_URL") else "",
    }
