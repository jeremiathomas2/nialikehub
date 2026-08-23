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


class BotFAQ(models.Model):
    question = models.CharField(max_length=200)
    keywords = models.CharField(
        max_length=300, blank=True, default="",
        help_text="Comma-separated words used to match user messages.",
    )
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.question

    def keyword_list(self):
        return [k.strip().lower() for k in (self.keywords or "").split(",") if k.strip()]


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
    "BOT_ENABLED": "1",
    "BOT_NAME": "Nia",
    "BOT_GREETING": "Hi! I'm Nia, your {app} assistant. Ask me about signing in, creating an account or what {app} can do.",
    "BOT_NUDGE_TEXT": "Hi there! Need help signing in?",
    "BOT_QUICK_REPLIES": "How do I sign in?\nHow does registration work?\nWhat can {app} do?",
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
    ctx = {
        "brand_name": brand_name,
        "app_name": brand_name,
        "currency": get_setting("currency", "TZS"),
        "default_primary_color": get_setting("default_primary_color", "#1C3A2E"),
        "default_accent_color": get_setting("default_accent_color", "#FFFDD0"),
        "footer_text": get_setting("footer_text", ""),
        "app_url": settings.APP_URL if hasattr(settings, "APP_URL") else "",
    }

    def _bot(value):
        return value.replace("{app}", brand_name)

    ctx.update(
        {
            "bot_enabled": bot_enabled(),
            "bot_name": _bot(get_setting("BOT_NAME", DEFAULT_SETTINGS["BOT_NAME"])),
            "bot_greeting": _bot(get_setting("BOT_GREETING", DEFAULT_SETTINGS["BOT_GREETING"])),
            "bot_nudge": _bot(get_setting("BOT_NUDGE_TEXT", DEFAULT_SETTINGS["BOT_NUDGE_TEXT"])),
            "bot_chips": [
                *(_bot(line.strip()) for line in get_setting(
                    "BOT_QUICK_REPLIES", DEFAULT_SETTINGS["BOT_QUICK_REPLIES"]
                ).splitlines() if line.strip()),
                *(faq.question for faq in BotFAQ.objects.filter(is_enabled=True)[:8]),
            ],
        }
    )
    return ctx


def bot_enabled():
    try:
        return (get_setting("BOT_ENABLED", "1") or "1") == "1"
    except Exception:
        return True
