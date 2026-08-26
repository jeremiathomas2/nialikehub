from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from apps.accounts.decorators import get_event_for
from apps.core.services import audit
from apps.events.models import Event, Guest

from .models import MessageLog, MessageTemplate, WhatsAppCard
from .services import queue_messages


@login_required
def messages_view(request, event_id):
    event = get_event_for(request.user, event_id)
    if not event:
        return HttpResponseForbidden("Forbidden")

    if request.method == "POST":
        op = request.POST.get("op", "")
        if op == "send":
            channel = request.POST.get("channel", "sms")
            if channel not in ("sms", "whatsapp"):
                channel = "sms"
            message = request.POST.get("message", "").strip()
            target = request.POST.get("target", "all")
            if not message:
                messages.error(request, "Message text is required.")
            else:
                guests_qs = Guest.objects.filter(event=event).exclude(phone__isnull=True).exclude(phone="")
                if target == "single":
                    gid = int(request.POST.get("guest_id", 0) or 0)
                    guests_qs = guests_qs.filter(pk=gid)
                count = queue_messages(event, request.user, channel, message, list(guests_qs))
                audit(request, "messages_queued", "events", event.pk, {"count": count, "channel": channel})
                messages.success(request, f"{count} message(s) queued.")
        elif op == "template_create":
            name = request.POST.get("name", "").strip()
            body = request.POST.get("body", "").strip()
            if name and body:
                MessageTemplate.objects.create(
                    user=request.user,
                    name=name[:120],
                    channel=request.POST.get("channel", "sms"),
                    body=body,
                )
                messages.success(request, "Template saved.")
        return redirect("messaging:messages", event_id=event.pk)

    logs = (
        MessageLog.objects.filter(event=event)
        .select_related("guest")
        .order_by("-pk")[:100]
    )
    templates = MessageTemplate.objects.filter(Q(user=request.user) | Q(is_system=True)).order_by("-pk")
    guests = Guest.objects.filter(event=event).order_by("name")
    return render(
        request,
        "messaging/messages.html",
        {
            "event": event,
            "logs": logs,
            "templates": templates,
            "guests": guests,
            "active": "messages",
            "page_title": "Templates & Logs",
            "page_eyebrow": "Messages",
        },
    )


@login_required
def cards_view(request, event_id):
    event = get_event_for(request.user, event_id)
    if not event:
        return HttpResponseForbidden("Forbidden")

    if request.method == "POST":
        op = request.POST.get("op", "")
        if op == "create":
            is_default = bool(request.POST.get("is_default"))
            if is_default:
                WhatsAppCard.objects.filter(event=event).update(is_default=False)
            WhatsAppCard.objects.create(
                event=event,
                name=request.POST.get("name", "")[:120] or "Main Invitation",
                style=request.POST.get("style", "classic")[:50] or "classic",
                headline=request.POST.get("headline", "")[:190] or "You are invited",
                message=request.POST.get("message", "")[:4000],
                primary_color=request.POST.get("primary_color", event.primary_color)[:20],
                accent_color=request.POST.get("accent_color", event.accent_color)[:20],
                is_default=is_default,
            )
            audit(request, "card_created", "whatsapp_cards", None, {"event_id": event.pk})
            messages.success(request, "Card saved.")
        elif op == "set_default":
            cid = int(request.POST.get("card_id", 0))
            WhatsAppCard.objects.filter(event=event).update(is_default=False)
            WhatsAppCard.objects.filter(pk=cid, event=event).update(is_default=True)
            messages.success(request, "Default card updated.")
        elif op == "delete":
            cid = int(request.POST.get("card_id", 0))
            WhatsAppCard.objects.filter(pk=cid, event=event).delete()
            messages.success(request, "Card deleted.")
        return redirect("messaging:cards", event_id=event.pk)

    cards = WhatsAppCard.objects.filter(event=event).order_by("-is_default", "-pk")
    public_url = request.build_absolute_uri(f"/i/{event.public_token}/")
    return render(
        request,
        "messaging/cards.html",
        {
            "event": event,
            "cards": cards,
            "public_url": public_url,
            "styles": WhatsAppCard.Style.choices,
            "active": "cards",
            "page_title": "Card Gallery",
            "page_eyebrow": "WhatsApp Cards",
        },
    )
