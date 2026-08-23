import json
from datetime import datetime
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Payment, Pledge


def _dec(value):
    return Decimal(str(value))


def provider_config():
    """PalmPesa config: DB overrides (Gateway & System page) with env fallback."""
    from apps.core.models import Setting

    cfg = dict(settings.PALMPESA)
    db_map = {
        "PALMPESA_ENABLED": "ENABLED",
        "PALMPESA_BASE_URL": "BASE_URL",
        "PALMPESA_USER_ID": "USER_ID",
        "PALMPESA_API_TOKEN": "API_TOKEN",
        "PALMPESA_TOKEN_PATH": "TOKEN_PATH",
        "PALMPESA_INITIATE_PATH": "INITIATE_PATH",
        "PALMPESA_STATUS_PATH": "STATUS_PATH",
        "PALMPESA_WEBHOOK_SECRET": "WEBHOOK_SECRET",
    }
    keys = set(Setting.objects.filter(setting_key__in=db_map).values_list("setting_key", flat=True))
    for env_key, cfg_key in db_map.items():
        if env_key in keys:
            val = Setting.objects.get(setting_key=env_key).setting_value
            if cfg_key == "ENABLED":
                cfg[cfg_key] = str(val).strip().lower() in ("1", "true", "yes", "on")
            elif val not in (None, ""):
                cfg[cfg_key] = val
    return cfg


def _request(url, payload, headers):
    try:
        resp = requests.request(
            "POST",
            url,
            json=payload,
            headers=headers,
            timeout=30,
        )
        ok = 200 <= resp.status_code < 300
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}
        return {"ok": ok, "status": resp.status_code, "data": data, "error": None if ok else resp.text[:200]}
    except requests.RequestException as exc:
        return {"ok": False, "status": 0, "data": {}, "error": str(exc)[:200]}


def palmpesa_request(path, payload):
    cfg = provider_config()
    if not cfg["ENABLED"]:
        return {"ok": False, "status": 0, "data": {}, "error": "PalmPesa is not configured."}
    headers = {
        "Authorization": f"Bearer {cfg['API_TOKEN']}",
        "X-API-Token": cfg["API_TOKEN"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if cfg["USER_ID"]:
        headers["X-User-ID"] = cfg["USER_ID"]
    return _request(f"{cfg['BASE_URL'].rstrip('/')}/{path.lstrip('/')}", payload, headers)


def generate_reference(prefix="NIA"):
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{timezone.now().microsecond % 10000:04d}"


def _callback_url():
    base = getattr(settings, "APP_URL", "") or "http://127.0.0.1:8000"
    return base.rstrip("/") + "/webhook/palmpesa/"


def initiate_payment(event, guest=None, pledge=None, amount=0, phone=""):
    """Create a pending payment and push it to PalmPesa. Returns (payment, result)."""
    amount = _dec(amount)
    reference = generate_reference()
    payment = Payment.objects.create(
        event=event,
        pledge=pledge,
        guest=guest,
        provider="palmpesa",
        reference=reference,
        amount=amount,
        currency="TZS",
        phone=phone,
        status=Payment.Status.PENDING,
    )
    # PalmPesa "Webhook Payment" endpoint requires these exact fields.
    # Their API rejects names with fewer than 2 words.
    payer_name = (guest.name if guest else getattr(event.user, "name", "") or "").strip()
    if len(payer_name.split()) < 2:
        payer_name = f"{payer_name} Customer".strip() or "Nialike Customer"
    payer_email = ((guest.email if guest else None) or getattr(event.user, "email", ""))[:190]
    payload = {
        "name": payer_name,
        "email": payer_email or f"{reference.lower()}@nialike.local",
        "phone": phone,
        "amount": int(amount) if amount == amount.to_integral_value() else float(amount),
        "transaction_id": reference,
        "address": "Dar es Salaam",
        "postcode": "11111",
        "callback_url": _callback_url(),
    }
    result = palmpesa_request(provider_config()["INITIATE_PATH"], payload)
    data = result.get("data") or {}
    payment.status = Payment.Status.PROCESSING if result["ok"] else Payment.Status.FAILED
    payment.provider_reference = data.get("order_id") or data.get("transaction_id") or data.get("reference")
    payment.raw_response = json.dumps(data, default=str)
    payment.save(update_fields=["status", "provider_reference", "raw_response", "updated_at"])
    return payment, result


def palmpesa_order_status(order_id):
    cfg = provider_config()
    if not cfg["ENABLED"]:
        return {"ok": False, "status": 0, "data": {}, "error": "PalmPesa is not configured."}
    return palmpesa_request(cfg.get("STATUS_PATH", "/order-status"), {"order_id": order_id})


def _map_provider_status(value):
    status = str(value or "").strip().lower()
    if status in ("success", "successful", "paid", "completed"):
        return Payment.Status.SUCCESS
    if status in ("failed", "failure", "cancelled", "canceled"):
        return Payment.Status.FAILED
    return Payment.Status.PROCESSING


def _apply_payment_status(payment, new_status, provider_ref=None, raw=None):
    already_success = payment.status == Payment.Status.SUCCESS
    payment.status = new_status
    if provider_ref:
        payment.provider_reference = provider_ref
    if raw is not None:
        payment.raw_response = json.dumps(raw, default=str)
    if new_status == Payment.Status.SUCCESS and not payment.paid_at:
        payment.paid_at = timezone.now()
    payment.save(update_fields=["status", "provider_reference", "raw_response", "paid_at", "updated_at"])
    if new_status == Payment.Status.SUCCESS and not already_success:
        apply_success_to_pledge(payment)


def refresh_payment_status(payment):
    """Poll PalmPesa Get Order Status and apply the authoritative result."""
    if not payment.provider_reference:
        return payment.status, {"ok": False, "error": "No PalmPesa order id stored."}
    result = palmpesa_order_status(payment.provider_reference)
    data = result.get("data") or {}
    rows = data.get("data") if isinstance(data, dict) else None
    row = rows[0] if isinstance(rows, list) and rows else {}
    reported = row.get("payment_status") or data.get("payment_status")
    new_status = _map_provider_status(reported)
    if reported:
        _apply_payment_status(
            payment,
            new_status,
            provider_ref=row.get("order_id"),
            raw=data,
        )
    return payment.status, result


def apply_success_to_pledge(payment):
    """BR-005..008: allocate a successful payment to its pledge and update status."""
    pledge = payment.pledge
    if not pledge:
        return
    with transaction.atomic():
        Pledge.objects.filter(pk=pledge.pk).update(
            paid_amount=F("paid_amount") + payment.amount,
            updated_at=timezone.now(),
        )
        pledge.refresh_from_db()
        if pledge.paid_amount >= pledge.amount:
            pledge.status = Pledge.Status.PAID
        elif pledge.paid_amount > 0:
            pledge.status = Pledge.Status.PARTIAL
        pledge.save(update_fields=["status", "updated_at"])


def record_manual_payment(pledge, amount):
    """Manual/offline payment recording (provider='manual', success immediately)."""
    amount = _dec(amount)
    reference = generate_reference("MAN")
    with transaction.atomic():
        payment = Payment.objects.create(
            event=pledge.event,
            pledge=pledge,
            guest=pledge.guest,
            provider="manual",
            reference=reference,
            amount=amount,
            currency="TZS",
            status=Payment.Status.SUCCESS,
            paid_at=timezone.now(),
        )
        new_paid = pledge.paid_amount + amount
        pledge.paid_amount = new_paid
        pledge.status = Pledge.Status.PAID if new_paid >= pledge.amount else Pledge.Status.PARTIAL
        pledge.save(update_fields=["paid_amount", "status", "updated_at"])
    return payment


def process_webhook(raw_body, payload, signature):
    """Validate + apply a PalmPesa webhook. Returns (ok, http_status).

    PalmPesa callbacks are not HMAC-signed; they carry {"order_id", "payment_status"}.
    If a valid signature is present we honour it; otherwise the reported status is
    confirmed against the authoritative Get Order Status endpoint before applying.
    """
    import hashlib
    import hmac

    secret = provider_config()["WEBHOOK_SECRET"]
    signature_valid = False
    if secret and signature:
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        signature_valid = hmac.compare_digest(expected, signature)

    order_id = str(payload.get("order_id") or "").strip()
    reference = str(payload.get("reference") or payload.get("merchant_reference") or "").strip()
    provider_ref = payload.get("transaction_id") or payload.get("provider_reference")

    if reference:
        payment = Payment.objects.filter(reference=reference).first()
    elif order_id:
        payment = Payment.objects.filter(provider_reference=order_id).first()
    else:
        payment = None

    if payment is None:
        # Unknown transaction - acknowledge so the gateway does not retry forever.
        return True, 200

    reported_status = payload.get("payment_status") or payload.get("status")
    new_status = _map_provider_status(reported_status)

    if not signature_valid and order_id:
        # Confirm untrusted reports against PalmPesa directly.
        result = palmpesa_order_status(order_id)
        data = result.get("data") or {}
        rows = data.get("data") if isinstance(data, dict) else None
        row = rows[0] if isinstance(rows, list) and rows else {}
        polled = row.get("payment_status")
        if polled:
            new_status = _map_provider_status(polled)
        if isinstance(data, dict) and data:
            payload = {**payload, "polled": data}

    _apply_payment_status(payment, new_status, provider_ref=order_id or provider_ref, raw=payload)
    return True, 200
