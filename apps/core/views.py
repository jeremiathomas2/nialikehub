import json
import re
import time
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.events.models import Event, Guest
from apps.messaging.models import MessageLog
from apps.core.services import audit

from .models import AuditLog, BotFAQ, DEFAULT_SETTINGS, bot_enabled, get_setting, set_setting


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


# ==================== Chatbot assistant ====================

BOT_INTENTS = [
    {
        "keywords": ["hello", "hi", "hey", "jambo", "habari", "mambo", "shikamoo", "good morning",
                     "good afternoon", "good evening", "habari yako"],
        "reply": "Hello! How can I help you today? You can ask about signing in, creating an account or what {app} can do.",
        "chips": ["How do I sign in?", "How does registration work?", "What can {app} do?"],
    },
    {
        "keywords": ["password", "forgot", "reset password", "incorrect", "wrong password",
                     "cannot log", "can't log", "cant log", "locked", "invalid"],
        "reply": ("Double-check that Caps Lock is off and you're using the email you registered with. "
                  "Passwords are case-sensitive. If you still can't sign in, ask a system administrator to reset it for you."),
        "chips": ["How does registration work?", "Demo accounts"],
    },
    {
        "keywords": ["demo", "test account", "sample account", "admin@nialike.test", "@demo.nialike.test"],
        "reply": ("On this development instance you can explore with the super admin admin@nialike.test / password "
                  "or seeded demo organizers such as amina@demo.nialike.test and joseph@demo.nialike.test (password Demo@1234)."),
        "chips": ["How do I sign in?"],
    },
    {
        "keywords": ["register", "registration", "sign up", "signup", "create account", "new account",
                     "approval", "approve", "pending", "activate", "activated", "join"],
        "reply": ("Choose \"Create an account\" below the sign-in form and fill in your details. "
                  "New accounts start as pending - a system administrator must approve them before you can sign in."),
        "chips": ["How do I sign in?", "What can {app} do?"],
    },
    {
        "keywords": ["invitation", "invite", "event", "events", "guest", "guests", "rsvp",
                     "pledge", "pledges", "payment", "payments", "whatsapp", "card", "sms", "message",
                     "feature", "features", "what can", "do for me", "about"],
        "reply": ("{app} helps you plan celebrations end to end: build beautiful digital invitations, manage guests and RSVPs, "
                  "track pledges, record payments, send SMS/WhatsApp messages and share public event pages with QR-friendly links."),
        "chips": ["How does registration work?", "How do I sign in?"],
    },
    {
        "keywords": ["contact", "support", "admin", "administrator", "help me", "human", "person", "call", "phone", "email"],
        "reply": ("For anything beyond my answers, please reach out to your system administrator directly - "
                  "they can approve accounts, reset passwords and configure the platform from the Administration area."),
        "chips": ["How do I sign in?"],
    },
]

BOT_FALLBACK = (
    "I'm not sure about that one yet. Try asking about signing in, registering an account, "
    "or what {app} can do - or contact your system administrator."
)

BOT_FALLBACK_CHIPS = ["How do I sign in?", "How does registration work?", "What can {app} do?"]


def _bot_fill(text):
    return text.replace("{app}", get_setting("brand_name", "Nialike"))


def _match_intent(message):
    msg = re.sub(r"[^a-z0-9@\s]", " ", message.lower())
    best, best_score = None, 0
    for intent in BOT_INTENTS:
        score = sum(1 for kw in intent["keywords"] if kw in msg)
        if score > best_score:
            best, best_score = intent, score
    if best:
        return _bot_fill(best["reply"]), [_bot_fill(c) for c in best["chips"]]
    faq_best, faq_score = None, 0
    for faq in BotFAQ.objects.filter(is_enabled=True):
        score = sum(1 for kw in faq.keyword_list() if kw in msg)
        if faq.question.lower() in msg:
            score += 3
        if score > faq_score:
            faq_best, faq_score = faq, score
    if faq_best:
        return faq_best.answer, []
    return _bot_fill(BOT_FALLBACK), [_bot_fill(c) for c in BOT_FALLBACK_CHIPS]


BOT_RATE_LIMIT = 20
BOT_RATE_WINDOW = 60


@require_POST
def assistant_view(request):
    brand_name = get_setting("brand_name", "Nialike")
    if not bot_enabled():
        return JsonResponse({"ok": False, "error": "Assistant disabled."}, status=404)

    now = time.time()
    bucket = request.session.get("bot_rl") or {"t": int(now), "n": 0}
    if int(bucket["t"]) != int(now // BOT_RATE_WINDOW):
        bucket = {"t": int(now // BOT_RATE_WINDOW), "n": 0}
    bucket["n"] += 1
    request.session["bot_rl"] = bucket
    if bucket["n"] > BOT_RATE_LIMIT:
        return JsonResponse({"ok": False, "error": "Too many messages - please slow down."}, status=429)

    message = ""
    if request.content_type and "application/json" in request.content_type:
        try:
            message = str(json.loads(request.body or b"{}").get("message", ""))
        except (ValueError, TypeError):
            message = ""
    else:
        message = request.POST.get("message", "")
    message = message.strip()[:500]
    if not message:
        return JsonResponse({"ok": False, "error": "Empty message."}, status=400)

    reply, chips = _match_intent(message)
    return JsonResponse({"ok": True, "reply": reply, "chips": chips})


@login_required
@user_passes_test(_admin_check)
def bot_config_view(request):
    group = request.POST.get("group", "")

    if request.method == "POST" and group == "settings":
        set_setting("BOT_ENABLED", "1" if request.POST.get("enabled") else "0")
        set_setting("BOT_NAME", request.POST.get("name", "").strip()[:60] or DEFAULT_SETTINGS["BOT_NAME"])
        set_setting("BOT_GREETING", request.POST.get("greeting", "").strip()[:400])
        set_setting("BOT_NUDGE_TEXT", request.POST.get("nudge", "").strip()[:200])
        set_setting("BOT_QUICK_REPLIES", "\n".join(
            line.strip()[:120] for line in request.POST.get("quick_replies", "").splitlines() if line.strip()
        ))
        audit(request, "bot_config_changed", "settings", None, {"part": "assistant"})
        messages.success(request, "Chatbot settings saved.")
        return redirect("core:bot_config")

    elif request.method == "POST" and group in ("faq_add", "faq_update"):
        if group == "faq_update":
            faq = get_object_or_404(BotFAQ, pk=request.POST.get("id", 0))
            faq.question = request.POST.get("question", "").strip()[:200]
            faq.keywords = request.POST.get("keywords", "").strip()[:300]
            faq.answer = request.POST.get("answer", "").strip()[:2000]
            faq.order = int(request.POST.get("order", 0) or 0)
            faq.is_enabled = bool(request.POST.get("is_enabled"))
            faq.save()
            audit(request, "bot_faq_updated", "bot_faq", faq.pk)
            messages.success(request, "FAQ updated.")
        else:
            question = request.POST.get("question", "").strip()[:200]
            answer = request.POST.get("answer", "").strip()[:2000]
            if not question or not answer:
                messages.error(request, "Question and answer are required.")
            else:
                faq = BotFAQ.objects.create(
                    question=question,
                    keywords=request.POST.get("keywords", "").strip()[:300],
                    answer=answer,
                    order=int(request.POST.get("order", 0) or 0),
                    is_enabled=bool(request.POST.get("is_enabled")),
                )
                audit(request, "bot_faq_created", "bot_faq", faq.pk)
                messages.success(request, "FAQ added.")
        return redirect("core:bot_config")

    elif request.method == "POST" and group == "faq_delete":
        faq = get_object_or_404(BotFAQ, pk=request.POST.get("id", 0))
        faq.delete()
        audit(request, "bot_faq_deleted", "bot_faq", faq.pk)
        messages.success(request, "FAQ deleted.")
        return redirect("core:bot_config")

    context = {
        "faqs": BotFAQ.objects.all(),
        "enabled": bot_enabled(),
        "bot_name": get_setting("BOT_NAME", DEFAULT_SETTINGS["BOT_NAME"]),
        "greeting": get_setting("BOT_GREETING", DEFAULT_SETTINGS["BOT_GREETING"]),
        "nudge": get_setting("BOT_NUDGE_TEXT", DEFAULT_SETTINGS["BOT_NUDGE_TEXT"]),
        "quick_replies": get_setting("BOT_QUICK_REPLIES", DEFAULT_SETTINGS["BOT_QUICK_REPLIES"]),
        "active": "bot",
        "page_title": "Chatbot Configuration",
        "page_eyebrow": "Admin",
    }
    return render(request, "core/bot_config.html", context)
