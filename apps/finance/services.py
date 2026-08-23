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
    payload = {
        "reference": reference,
        "amount": float(amount),
        "currency": "TZS",
        "phone": phone,
        "callback_url": "/webhook/palmpesa/",
        "description": "Nialike event payment",
    }
    result = palmpesa_request(provider_config()["INITIATE_PATH"], payload)
    data = result.get("data") or {}
    payment.status = Payment.Status.PROCESSING if result["ok"] else Payment.Status.FAILED
    payment.provider_reference = data.get("transaction_id") or data.get("reference")
    payment.raw_response = json.dumps(data, default=str)
    payment.save(update_fields=["status", "provider_reference", "raw_response", "updated_at"])
    return payment, result


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
    """Validate + apply a PalmPesa webhook. Returns (ok, http_status)."""
    import hashlib
    import hmac

    secret = provider_config()["WEBHOOK_SECRET"]
    if not secret:
        # No secret configured -> refuse to trust any webhook payload.
        return False, 401
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        return False, 401

    reference = payload.get("reference") or payload.get("merchant_reference") or ""
    status = str(payload.get("status") or payload.get("payment_status") or "").lower()
    provider_ref = payload.get("transaction_id") or payload.get("provider_reference")

    if not reference:
        return True, 200

    payment = Payment.objects.filter(reference=reference).first()
    if not payment:
        return True, 200

    if status in ("success", "successful", "paid", "completed"):
        mapped = Payment.Status.SUCCESS
    elif status in ("failed", "failure", "cancelled", "canceled"):
        mapped = Payment.Status.FAILED
    else:
        mapped = Payment.Status.PROCESSING

    # Idempotency: never double-apply a success.
    already_success = payment.status == Payment.Status.SUCCESS
    payment.status = mapped
    payment.provider_reference = provider_ref or payment.provider_reference
    payment.raw_response = json.dumps(payload, default=str)
    if mapped == Payment.Status.SUCCESS and not payment.paid_at:
        payment.paid_at = timezone.now()
    payment.save(update_fields=["status", "provider_reference", "raw_response", "paid_at", "updated_at"])

    if mapped == Payment.Status.SUCCESS and not already_success:
        apply_success_to_pledge(payment)

    return True, 200
