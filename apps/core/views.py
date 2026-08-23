import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.events.models import Event, Guest
from apps.messaging.models import MessageLog
from apps.core.services import audit

from .models import AuditLog, get_setting, set_setting


def _money_stats(qs_events):
    pledged = (
        qs_events.aggregate(v=Coalesce(Sum("pledges__amount"), Value(0), output_field=DecimalField()))["v"] or 0
    )
    collected = (
        qs_events.aggregate(
            v=Coalesce(Sum("payments__amount", filter=Q(payments__status="success")), Value(0), output_field=DecimalField())
        )["v"]
        or 0
    )
    return float(pledged), float(collected)


@login_required
def dashboard(request):
    u = request.user
    if u.is_admin:
        stats = {
            "Total Events": Event.objects.count(),
            "Total Guests": Guest.objects.count(),
            "Pending Approvals": User.objects.filter(role=User.Role.USER, status=User.Status.PENDING).count(),
            "Messages Sent": MessageLog.objects.exclude(status="queued").count(),
        }
        event_qs = Event.objects.all()
        recent = AuditLog.objects.select_related("user").order_by("-pk")[:8]
    else:
        event_qs = Event.objects.filter(user=u)
        stats = {
            "My Events": event_qs.count(),
            "Guests": Guest.objects.filter(event__user=u).count(),
            "Published": event_qs.filter(status=Event.Status.PUBLISHED).count(),
            "Messages Sent": MessageLog.objects.filter(event__user=u).exclude(status="queued").count(),
        }
        recent = event_qs.order_by("-pk")[:6]

    pledged, collected = _money_stats(event_qs)
    outstanding = max(pledged - collected, 0)

    # Collections chart: successful payments grouped by month, last 6 months.
    six_months_ago = timezone.now() - timedelta(days=183)
    chart_rows = (
        event_qs.filter(payments__status="success", payments__paid_at__gte=six_months_ago)
        .values_list("payments__paid_at", "payments__amount")
    )
    buckets = {}
    now = timezone.now()
    for i in range(5, -1, -1):
        m = (now.month - i - 1) % 12 + 1
        y = now.year + (now.month - i - 1) // 12
        buckets[(y, m)] = 0.0
    for paid_at, amount in chart_rows:
        key = (paid_at.year, paid_at.month)
        if key in buckets:
            buckets[key] += float(amount)
    max_val = max(buckets.values(), default=0) or 1
    chart = [
        {
            "label": timezone.make_aware(timezone.datetime(y, m, 1)).strftime("%b"),
            "value": v,
            "height": int(round(v / max_val * 100)),
        }
        for (y, m), v in buckets.items()
    ]

    context = {
        "stats": stats,
        "pledged": pledged,
        "collected": collected,
        "outstanding": outstanding,
        "chart": chart,
        "recent": recent,
        "active": "dashboard",
        "page_title": "Dashboard",
        "page_eyebrow": "Digital Invitations Platform",
    }
    return render(request, "dashboard.html", context)


def _admin_check(user):
    return user.is_authenticated and user.is_admin


@login_required
@user_passes_test(_admin_check)
def gateway_view(request):
    if request.method == "POST":
        group = request.POST.get("group", "")
        if group == "general":
            set_setting("brand_name", request.POST.get("brand_name", "").strip()[:100])
            set_setting("default_primary_color", request.POST.get("default_primary_color", "#1C3A2E")[:20])
            set_setting("default_accent_color", request.POST.get("default_accent_color", "#FFFDD0")[:20])
            set_setting("footer_text", request.POST.get("footer_text", "")[:250])
            audit(request, "settings_updated", "settings", None, {"group": "general"})
            messages.success(request, "General settings saved.")
        elif group == "nextsms":
            set_setting("NEXTSMS_ENABLED", "1" if request.POST.get("enabled") else "0")
            set_setting("NEXTSMS_BASE_URL", request.POST.get("base_url", "")[:255])
            set_setting("NEXTSMS_SENDER_ID", request.POST.get("sender_id", "")[:30])
            api_key = request.POST.get("api_key", "").strip()
            if api_key:
                set_setting("NEXTSMS_API_KEY", api_key, is_secret=True)
            audit(request, "gateway_config_changed", "settings", None, {"provider": "nextsms"})
            messages.success(request, "NextSMS settings saved.")
        elif group == "test_sms":
            phone = request.POST.get("phone", "").strip()
            text = request.POST.get("message", "").strip()[:480]
            if not phone or not text:
                messages.error(request, "Phone number and message are required for the SMS test.")
            else:
                from apps.messaging.services import nextsms_send

                result = nextsms_send(phone, text)
                if result["ok"]:
                    audit(request, "gateway_test_sms", "settings", None, {"provider": "nextsms", "to": phone})
                    messages.success(request, f"Test SMS sent (HTTP {result['status']}): {json.dumps(result['data'])[:300]}")
                else:
                    messages.error(request, f"Test SMS failed: {result['error'] or 'Unknown error'}")
        elif group == "palmpesa":
            set_setting("PALMPESA_ENABLED", "1" if request.POST.get("enabled") else "0")
            set_setting("PALMPESA_BASE_URL", request.POST.get("base_url", "")[:255])
            set_setting("PALMPESA_INITIATE_PATH", request.POST.get("initiate_path", "/payments/initiate")[:120])
            set_setting("PALMPESA_STATUS_PATH", request.POST.get("status_path", "/payments/status")[:120])
            set_setting("PALMPESA_TOKEN_PATH", request.POST.get("token_path", "/token")[:120])
            user_id = request.POST.get("user_id", "").strip()
            if user_id:
                set_setting("PALMPESA_USER_ID", user_id)
            token = request.POST.get("api_token", "").strip()
            if token:
                set_setting("PALMPESA_API_TOKEN", token, is_secret=True)
            secret = request.POST.get("webhook_secret", "").strip()
            if secret:
                set_setting("PALMPESA_WEBHOOK_SECRET", secret, is_secret=True)
            audit(request, "gateway_config_changed", "settings", None, {"provider": "palmpesa"})
            messages.success(request, "PalmPesa settings saved.")
        return redirect("core:gateway")

    from apps.finance.services import provider_config
    from apps.messaging.services import nextsms_config

    ns = nextsms_config()
    pc = provider_config()
    context = {
        "ns": ns,
        "pc": pc,
        "brand_name": get_setting("brand_name"),
        "primary_color": get_setting("default_primary_color"),
        "accent_color": get_setting("default_accent_color"),
        "footer_text": get_setting("footer_text"),
        "active": "settings",
        "page_title": "Gateway & System",
        "page_eyebrow": "Admin",
    }
    return render(request, "core/gateway.html", context)


@login_required
@user_passes_test(_admin_check)
def audit_view(request):
    rows = AuditLog.objects.select_related("user").order_by("-pk")[:200]
    return render(
        request,
        "core/audit.html",
        {"rows": rows, "active": "audit", "page_title": "Audit Log", "page_eyebrow": "Admin"},
    )
