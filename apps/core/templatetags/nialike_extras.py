from django import template

register = template.Library()


@register.filter
def money(value):
    """Format a number as TZS currency, matching the PHP money() helper."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "0 TZS"
    if n == int(n):
        return f"{int(n):,} TZS"
    return f"{n:,.2f} TZS"


@register.filter
def initials(name):
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "NA"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


STATUS_BADGE = {
    # events
    "published": "b-green",
    "draft": "b-gold",
    "closed": "b-muted",
    # users
    "approved": "b-green",
    "pending": "b-gold",
    "suspended": "b-red",
    # guests
    "rsvp_yes": "b-green",
    "checked_in": "b-blue",
    "sent": "b-blue",
    "delivered": "b-green",
    "viewed": "b-blue",
    "rsvp_no": "b-red",
    # pledges / payments / messages
    "paid": "b-green",
    "success": "b-green",
    "partial": "b-gold",
    "processing": "b-gold",
    "queued": "b-gold",
    "promised": "b-blue",
    "defaulted": "b-red",
    "failed": "b-red",
    "cancelled": "b-muted",
    "canceled": "b-muted",
    "refunded": "b-muted",
}


@register.filter
def badge(status):
    return STATUS_BADGE.get((status or "").lower(), "b-muted")


register.filter("status_badge", badge)


@register.filter
def status_label(status):
    mapping = {
        "rsvp_yes": "RSVP Yes",
        "rsvp_no": "RSVP No",
        "checked_in": "Checked In",
    }
    s = (status or "").lower()
    return mapping.get(s, (status or "").replace("_", " ").title())
