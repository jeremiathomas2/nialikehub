import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from apps.accounts.decorators import get_event_for, visible_events
from apps.core.services import audit
from apps.finance.models import Payment

from .models import Event, Guest


@login_required
def event_list(request):
    events = visible_events(request.user).select_related("user").order_by("-pk")
    guest_counts = {g["event_id"]: g["n"] for g in Guest.objects.values("event_id").annotate(n=Count("id"))}
    rsvp_counts = {
        g["event_id"]: g["n"]
        for g in Guest.objects.filter(invitation_status="rsvp_yes").values("event_id").annotate(n=Count("id"))
    }
    collected = {
        p["event_id"]: float(p["v"] or 0)
        for p in Payment.objects.filter(status="success")
        .values("event_id")
        .annotate(v=Coalesce(Sum("amount"), Value(0), output_field=DecimalField()))
    }
    rows = [
        {
            "obj": e,
            "guests": guest_counts.get(e.pk, 0),
            "rsvp": rsvp_counts.get(e.pk, 0),
            "collected": collected.get(e.pk, 0),
        }
        for e in events
    ]
    return render(
        request,
        "events/list.html",
        {"rows": rows, "active": "events", "page_title": "All Events", "page_eyebrow": "Events"},
    )


@login_required
def event_create(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        date = request.POST.get("event_date", "").strip()
        if not title or not date:
            messages.error(request, "Event title and date are required.")
            return render(
                request,
                "events/form.html",
                {"active": "events", "page_title": "Create Event", "page_eyebrow": "Events"},
            )
        slug = slugify(f"{title}-{time.strftime('%H%M%S')}")
        event = Event.objects.create(
            user=request.user,
            title=title[:180],
            slug=slug,
            event_type=request.POST.get("event_type", "General").strip()[:80] or "General",
            description=request.POST.get("description", "")[:5000],
            event_date=date,
            start_time=request.POST.get("start_time") or None,
            venue=request.POST.get("venue", "")[:255] or None,
            address=request.POST.get("address", "")[:255] or None,
            primary_color=request.POST.get("primary_color", "#1C3A2E")[:20] or "#1C3A2E",
            accent_color=request.POST.get("accent_color", "#FFFDD0")[:20] or "#FFFDD0",
            status=Event.Status.DRAFT if request.POST.get("op") != "publish" else Event.Status.PUBLISHED,
        )
        audit(request, "event_created", "events", event.pk, {"title": event.title})
        messages.success(request, "Event created." if event.status == Event.Status.DRAFT else "Event published.")
        return redirect("events:detail", event_id=event.pk)
    return render(
        request,
        "events/form.html",
        {
            "active": "events",
            "page_title": "Create Event",
            "page_eyebrow": "Events",
            "types": [
                ("Wedding", "Wedding"), ("Engagement", "Engagement"),
                ("Birthday", "Birthday"), ("Graduation", "Graduation"),
                ("Baby Shower", "Baby Shower"), ("Send-off", "Send-off"),
                ("Corporate", "Corporate"), ("General", "General"),
            ],
        },
    )


@login_required
def event_detail(request, event_id):
    event = get_event_for(request.user, event_id)
    if not event:
        return HttpResponseForbidden("Forbidden")

    if request.method == "POST":
        op = request.POST.get("op", "")
        if op == "publish":
            event.status = Event.Status.PUBLISHED
            event.save(update_fields=["status", "updated_at"])
            audit(request, "event_published", "events", event.pk)
            messages.success(request, "Event published.")
        elif op == "close":
            event.status = Event.Status.CLOSED
            event.save(update_fields=["status", "updated_at"])
            audit(request, "event_closed", "events", event.pk)
            messages.success(request, "Event closed.")
        elif op == "delete":
            audit(request, "event_deleted", "events", event.pk, {"title": event.title})
            event.delete()
            messages.success(request, "Event deleted.")
            return redirect("events:list")
        return redirect("events:detail", event_id=event.pk)

    guests = Guest.objects.filter(event=event)
    summary = {
        "Guests": guests.count(),
        "RSVP Yes": guests.filter(invitation_status=Guest.InvitationStatus.RSVP_YES).count(),
        "Pledge": float(
            event.pledges.aggregate(v=Coalesce(Sum("amount"), Value(0), output_field=DecimalField()))["v"] or 0
        ),
        "Collected": float(
            event.payments.filter(status="success")
            .aggregate(v=Coalesce(Sum("amount"), Value(0), output_field=DecimalField()))["v"]
            or 0
        ),
    }
    public_url = request.build_absolute_uri(f"/i/{event.public_token}/")
    return render(
        request,
        "events/detail.html",
        {
            "event": event,
            "summary": summary,
            "public_url": public_url,
            "active": "events",
            "page_title": f"Manage: {event.title}",
            "page_eyebrow": "Events",
        },
    )


@login_required
def guests_view(request, event_id):
    event = get_event_for(request.user, event_id)
    if not event:
        return HttpResponseForbidden("Forbidden")

    if request.method == "POST":
        op = request.POST.get("op", "")
        if op == "add":
            name = request.POST.get("name", "").strip()
            if not name:
                messages.error(request, "Guest name is required.")
            else:
                guest = Guest.objects.create(
                    event=event,
                    name=name[:150],
                    phone=request.POST.get("phone", "")[:30] or None,
                    email=request.POST.get("email", "")[:190] or None,
                    category=request.POST.get("category", "")[:100] or None,
                    seats=max(1, int(request.POST.get("seats", 1) or 1)),
                )
                audit(request, "guest_added", "guests", guest.pk, {"event_id": event.pk})
                messages.success(request, "Guest added.")
        elif op == "status":
            gid = int(request.POST.get("guest_id", 0))
            status = request.POST.get("status", "pending")
            valid = [s for s in Guest.InvitationStatus]
            if status in valid:
                Guest.objects.filter(pk=gid, event=event).update(
                    invitation_status=status, updated_at=timezone.now()
                )
                audit(request, "guest_status_changed", "guests", gid, {"status": status})
        elif op == "delete":
            gid = int(request.POST.get("guest_id", 0))
            Guest.objects.filter(pk=gid, event=event).delete()
            messages.success(request, "Guest removed.")
        return redirect("events:guests", event_id=event.pk)

    paid_sq = Coalesce(
        Sum("payments__amount", filter=Q(payments__status="success")), Value(0), output_field=DecimalField()
    )
    pledged_sq = Coalesce(Sum("pledges__amount"), Value(0), output_field=DecimalField())
    rows = (
        Guest.objects.filter(event=event)
        .annotate(paid=paid_sq, pledged=pledged_sq)
        .order_by("name")
    )
    return render(
        request,
        "events/guests.html",
        {
            "event": event,
            "rows": rows,
            "statuses": [s for s in Guest.InvitationStatus],
            "active": "guests",
            "page_title": "All Guests",
            "page_eyebrow": "Guests",
        },
    )


def public_event(request, token):
    event = Event.objects.filter(public_token=token, status__in=[Event.Status.PUBLISHED, Event.Status.CLOSED]).first()
    if not event:
        return render(request, "public/404.html", status=404)
    card = event.cards.filter(is_default=True).order_by("-pk").first()
    share_url = request.build_absolute_uri(f"/i/{event.public_token}/")
    return render(request, "public/event.html", {"event": event, "card": card, "share_url": share_url})


@require_POST
def rsvp_submit(request, token):
    guest = Guest.objects.select_related("event").filter(rsvp_token=token).first()
    if not guest:
        return render(request, "public/404.html", status=404)
    choice = request.POST.get("choice", "")
    if choice in ("yes", "no"):
        guest.invitation_status = (
            Guest.InvitationStatus.RSVP_YES if choice == "yes" else Guest.InvitationStatus.RSVP_NO
        )
        guest.save(update_fields=["invitation_status", "updated_at"])
        messages.success(request, "RSVP updated successfully.")
    return redirect("events:rsvp", token=guest.rsvp_token)


def rsvp_view(request, token):
    guest = Guest.objects.select_related("event").filter(rsvp_token=token).first()
    if not guest:
        return render(request, "public/404.html", status=404)
    return render(request, "public/rsvp.html", {"guest": guest})
