import json

from django.utils import timezone


def audit(request, action, entity="", entity_id=None, meta=None):
    """Record a critical business action in the audit log (mirrors PHP audit())."""
    from .models import AuditLog

    user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    ip = request.META.get("REMOTE_ADDR", "") if request is not None else ""
    AuditLog.objects.create(
        user=user,
        action=action,
        entity=entity,
        entity_id=entity_id,
        meta_json=json.dumps(meta or {}, default=str),
        ip_address=ip,
        created_at=timezone.now(),
    )
