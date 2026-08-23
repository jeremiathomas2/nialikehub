import json
import re
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import MessageLog, NotificationQueue


def normalize_phone(phone):
    digits = re.sub(r"\D+", "", str(phone or ""))
    if digits.startswith("0"):
        digits = "255" + digits[1:]
    return digits


def nextsms_config():
    """NextSMS config: DB overrides (Gateway & System page) with env fallback."""
    from apps.core.models import Setting

    cfg = dict(settings.NEXTSMS)
    db_map = {
        "NEXTSMS_ENABLED": "ENABLED",
        "NEXTSMS_BASE_URL": "BASE_URL",
        "NEXTSMS_API_KEY": "API_KEY",
        "NEXTSMS_SENDER_ID": "SENDER_ID",
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


def _nextsms_base_url(base_url):
    """Normalize base URL: strip trailing slashes and a trailing /api segment."""
    base = (base_url or "").rstrip("/")
    if base.lower().endswith("/api"):
        base = base[:-4]
    return base


def nextsms_send(phone, message):
    cfg = nextsms_config()
    if not cfg["ENABLED"] or not cfg["API_KEY"]:
        return {"ok": False, "status": 0, "data": {}, "error": "NextSMS is not configured. Set the API key in Gateway & System."}
    phone = normalize_phone(phone)
    payload = {
        "from": cfg["SENDER_ID"],
        "to": phone,
        "text": message,
        "flash": 0,
        "reference": f"nialike-{uuid.uuid4().hex[:10]}",
    }
    headers = {
        "Authorization": f"Bearer {cfg['API_KEY']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        resp = requests.post(
            f"{_nextsms_base_url(cfg['BASE_URL'])}/api/sms/v2/text/single",
            json=payload,
            headers=headers,
            timeout=30,
        )
        ok = 200 <= resp.status_code < 300
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}
        error = None
        if ok and isinstance(data, dict):
            # The v2 API returns HTTP 200 even for rejected messages; the real
            # outcome lives in messages[].status.groupName.
            msgs = data.get("messages")
            if isinstance(msgs, list) and msgs:
                rejected = [
                    (m.get("status") or {})
                    for m in msgs
                    if str((m.get("status") or {}).get("groupName") or "").upper() == "REJECTED"
                ]
                if rejected:
                    ok = False
                    error = "; ".join(
                        f"{s.get('name')}: {s.get('description')}".strip(": ").strip() for s in rejected
                    )[:200]
        if not ok and error is None:
            api_msg = ""
            if isinstance(data, dict):
                api_msg = str(data.get("message") or data.get("error") or "")
            error = (f"HTTP {resp.status_code}: {api_msg or resp.text}").strip()[:200]
        return {"ok": ok, "status": resp.status_code, "data": data, "error": error}
    except requests.RequestException as exc:
        return {"ok": False, "status": 0, "data": {}, "error": str(exc)[:200]}


PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_message(template_text, context):
    def replace(match):
        return str(context.get(match.group(1), match.group(0)))

    return PLACEHOLDER_RE.sub(replace, template_text or "")


@transaction.atomic
def queue_messages(event, user, channel, message, guests):
    """Queue a message for each guest and create matching message logs."""
    count = 0
    now = timezone.now()
    for guest in guests:
        if not guest.phone:
            continue
        to = normalize_phone(guest.phone)
        rendered = render_message(
            message,
            {
                "guest_name": guest.name,
                "event_name": event.title,
                "event_date": event.event_date.strftime("%d %b %Y"),
                "event_time": event.start_time.strftime("%H:%M") if event.start_time else "",
                "venue": event.venue or "",
                "event_link": f"/i/{event.public_token}/",
                "rsvp_link": f"/rsvp/{guest.rsvp_token}/",
            },
        )
        MessageLog.objects.create(
            event=event,
            guest=guest,
            user=user,
            channel=channel,
            recipient=to,
            message=rendered,
            provider="NextSMS" if channel == "sms" else "NextSMS/WhatsApp",
            status=MessageLog.Status.QUEUED,
        )
        NotificationQueue.objects.create(
            channel=channel,
            recipient=to,
            message=rendered,
            event=event,
            guest=guest,
            next_attempt_at=now,
        )
        count += 1
    return count


def process_queue(limit=50):
    """Worker: send queued notifications via NextSMS and update logs."""
    jobs = list(
        NotificationQueue.objects.filter(status="queued", next_attempt_at__lte=timezone.now()).order_by("id")[:limit]
    )
    sent = failed = 0
    for job in jobs:
        job.status = NotificationQueue.Status.PROCESSING
        job.save(update_fields=["status", "updated_at"])

        result = nextsms_send(job.recipient, job.message)
        new_status = NotificationQueue.Status.SENT if result["ok"] else NotificationQueue.Status.FAILED

        # Retry policy: up to 3 attempts with a 5-minute backoff.
        if not result["ok"] and job.attempts + 1 < 3:
            job.status = NotificationQueue.Status.QUEUED
            job.next_attempt_at = timezone.now() + timedelta(minutes=5)

        job.attempts += 1
        job.last_error = "" if result["ok"] else str(result.get("error") or json.dumps(result.get("data", {})))[:500]
        job.status = new_status if result["ok"] else job.status
        job.save(update_fields=["attempts", "last_error", "status", "next_attempt_at", "updated_at"])

        log = (
            MessageLog.objects.filter(event=job.event, guest=job.guest, recipient=job.recipient, status="queued")
            .order_by("-id")
            .first()
        )
        if log:
            log.status = MessageLog.Status.SENT if result["ok"] else MessageLog.Status.FAILED
            log.response_json = json.dumps(result, default=str)
            if result["ok"]:
                log.sent_at = timezone.now()
                data = result.get("data") if isinstance(result.get("data"), dict) else {}
                provider_id = (
                    data.get("message_id")
                    or data.get("id")
                    or ((data.get("messages") or [{}])[0].get("messageId"))
                    or ((data.get("messages") or [{}])[0].get("sendReference"))
                )
                if provider_id:
                    log.provider_message_id = str(provider_id)
            log.save(update_fields=["status", "response_json", "sent_at", "provider_message_id"])

        if result["ok"]:
            sent += 1
        else:
            failed += 1
    return {"processed": len(jobs), "sent": sent, "failed": failed}
