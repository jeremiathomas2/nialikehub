import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.decorators import get_event_for
from apps.core.models import get_setting
from apps.core.services import audit
from apps.events.models import Event, Guest
from apps.finance.services import (
    initiate_payment,
    process_webhook,
    record_manual_payment,
    refresh_payment_status,
)
from apps.messaging.services import normalize_phone, queue_messages

from .models import Payment, Pledge


@login_required
def pledges_view(request, event_id):
    event = get_event_for(request.user, event_id)
    if not event:
        return HttpResponseForbidden("Forbidden")

    if request.method == "POST":
        op = request.POST.get("op", "")
        if op == "add":
            guest = Guest.objects.filter(pk=int(request.POST.get("guest_id", 0)), event=event).first()
            if not guest:
                messages.error(request, "Guest not found.")
            else:
                try:
                    amount = float(request.POST.get("amount", 0) or 0)
                except ValueError:
                    amount = 0
                due = request.POST.get("due_date") or None
                Pledge.objects.create(
                    event=event,
                    guest=guest,
                    amount=amount,
                    due_date=due,
                    status=Pledge.Status.PROMISED,
                    note=request.POST.get("note", "")[:5000] or None,
                )
                audit(request, "pledge_created", "pledges", None, {"event_id": event.pk, "guest": guest.name})
                messages.success(request, "Pledge assigned.")
        elif op == "status":
            pid = int(request.POST.get("pledge_id", 0))
            st = request.POST.get("status", "")
            if st in [s for s in Pledge.Status]:
                Pledge.objects.filter(pk=pid, event=event).update(status=st, updated_at=timezone.now())
                audit(request, "pledge_status_changed", "pledges", pid, {"status": st})
        elif op == "record":
            pid = int(request.POST.get("pledge_id", 0))
            pledge = Pledge.objects.filter(pk=pid, event=event).first()
            if pledge:
                try:
                    amount = float(request.POST.get("amount", 0) or 0)
                except ValueError:
                    amount = 0
                if amount > 0:
                    record_manual_payment(pledge, amount)
                    audit(request, "payment_recorded", "payments", None, {"reference_prefix": "MAN", "amount": amount})
                    messages.success(request, "Payment recorded.")
        elif op == "remind":
            pid = int(request.POST.get("pledge_id", 0))
            pledge = (
                Pledge.objects.select_related("guest").filter(pk=pid, event=event).select_related("guest").first()
            )
            if pledge and pledge.guest.phone:
                balance = max(float(pledge.amount) - float(pledge.paid_amount), 0)
                text = (
                    f"Dear {pledge.guest.name}, your pledge balance for {event.title} "
                    f"is {balance:,.0f} TZS. Kindly complete your contribution."
                )
                count = queue_messages(event, request.user, "sms", text, [pledge.guest])
                audit(request, "pledge_reminder_queued", "pledges", pledge.pk, {"count": count})
                messages.success(request, f"{count} reminder queued.")
        return redirect("finance:pledges", event_id=event.pk)

    rows = (
        Pledge.objects.filter(event=event)
        .select_related("guest")
        .order_by("-pk")
    )
    total_pledged = float(rows.aggregate(v=Coalesce(Sum("amount"), Value(0), output_field=DecimalField()))["v"] or 0)
    total_paid = float(
        rows.aggregate(v=Coalesce(Sum("paid_amount"), Value(0), output_field=DecimalField()))["v"] or 0
    )
    overdue_count = rows.filter(due_date__lt=timezone.now().date()).exclude(
        status__in=[Pledge.Status.PAID, Pledge.Status.CANCELLED]
    ).count()

    return render(
        request,
        "finance/pledges.html",
        {
            "event": event,
            "rows": rows,
            "guests": Guest.objects.filter(event=event).order_by("name"),
            "total_pledged": total_pledged,
            "total_collected": total_paid,
            "outstanding": max(total_pledged - total_paid, 0),
            "overdue_count": overdue_count,
            "statuses": [s for s in Pledge.Status],
            "active": "pledges",
            "page_title": "Pledge Tracking",
            "page_eyebrow": "Pledges",
        },
    )


@login_required
def payments_view(request):
    event_id = int(request.POST.get("event_id", 0) or request.GET.get("event_id", 0) or 0)

    if request.method == "POST":
        op = request.POST.get("op", "")
        if op == "initiate":
            eid = int(request.POST.get("event_id", 0))
            event = get_event_for(request.user, eid)
            if not event:
                return HttpResponseForbidden("Forbidden")
            gid = int(request.POST.get("guest_id", 0) or 0)
            pid = int(request.POST.get("pledge_id", 0) or 0)
            guest = Guest.objects.filter(pk=gid, event=event).first() if gid else None
            pledge = Pledge.objects.filter(pk=pid, event=event).first() if pid else None
            try:
                amount = float(request.POST.get("amount", 0) or 0)
            except ValueError:
                amount = 0
            phone = normalize_phone(request.POST.get("phone", ""))
            if not event or amount <= 0 or not phone:
                messages.error(request, "Payment could not be initiated. Please check the details.")
                return redirect("finance:payments")
            payment, result = initiate_payment(
                event=event, guest=guest, pledge=pledge, amount=amount, phone=phone
            )
            audit(
                request,
                "payment_initiated",
                "payments",
                payment.pk,
                {"reference": payment.reference, "result": result["ok"]},
            )
            if result["ok"]:
                messages.success(request, "Payment request sent. Ask customer to complete the mobile-money prompt.")
            else:
                messages.error(request, f"PalmPesa request failed: {result.get('error') or 'API error'}")
            return redirect("finance:payments")
        elif op == "check_status":
            pid = int(request.POST.get("payment_id", 0))
            scope = Payment.objects.select_related("event", "guest")
            if not request.user.is_admin:
                scope = scope.filter(event__user=request.user)
            payment = scope.filter(pk=pid, provider="palmpesa").first()
            if not payment:
                messages.error(request, "Payment not found.")
            else:
                status, result = refresh_payment_status(payment)
                data = result.get("data") or {}
                err = result.get("error")
                if status == Payment.Status.SUCCESS:
                    messages.success(request, f"{payment.reference} confirmed as COMPLETED.")
                    audit(request, "payment_status_polled", "payments", payment.pk, {"status": "COMPLETED"})
                elif status == Payment.Status.FAILED:
                    messages.error(request, f"{payment.reference} is FAILED on PalmPesa.")
                    audit(request, "payment_status_polled", "payments", payment.pk, {"status": "FAILED"})
                elif err:
                    messages.error(request, f"Status check failed: {err}")
                else:
                    detail = ""
                    if isinstance(data, dict):
                        rows_ = data.get("data")
                        if isinstance(rows_, list) and rows_:
                            detail = str(rows_[0].get("payment_status") or "")
                    messages.info(request, f"{payment.reference} is still {detail or 'PENDING'} on PalmPesa.")
            return redirect("finance:payments")
        elif op == "refund_mark":
            pid = int(request.POST.get("payment_id", 0))
            updated = Payment.objects.filter(pk=pid).update(
                status=Payment.Status.REFUNDED, updated_at=timezone.now()
            )
            if updated:
                audit(request, "payment_refund_marked", "payments", pid)
                messages.success(request, "Payment marked refunded.")
            return redirect("finance:payments")

    events = (
        Event.objects.all() if request.user.is_admin else Event.objects.filter(user=request.user)
    ).order_by("title")

    base_qs = Payment.objects.select_related("event", "guest")
    if not request.user.is_admin:
        base_qs = base_qs.filter(event__user=request.user)
    rows = base_qs.order_by("-pk")[:200]
    if event_id:
        rows = rows.filter(event_id=event_id)

    guests_by_event = {}
    for ev in events:
        guests_by_event[ev.pk] = list(ev.guests.values("id", "name"))

    return render(
        request,
        "finance/payments.html",
        {
            "events": events,
            "guests_by_event": guests_by_event,
            "rows": rows,
            "selected_event_id": event_id,
            "palmpesa_enabled": get_setting("PALMPESA_ENABLED", "1" if settings.PALMPESA["ENABLED"] else "0") == "1",
            "active": "payments",
            "page_title": "Payment Ledger",
            "page_eyebrow": "Payments",
        },
    )


@csrf_exempt
def webhook_palmpesa(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)
    raw = request.body
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        payload = request.POST.dict()
    ok, status_code = process_webhook(raw, payload, request.headers.get("X-Webhook-Signature", ""))
    if not ok:
        return JsonResponse({"ok": False, "error": "invalid signature"}, status=401)
    return JsonResponse({"ok": True})
