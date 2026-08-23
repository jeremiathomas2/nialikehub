from apps.core.models import branding_context


def branding(request):
    ctx = {"brand": branding_context()}
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        from apps.events.models import Event

        qs = Event.objects.all() if user.is_admin else Event.objects.filter(user=user)
        latest = qs.order_by("-pk").only("id", "title").first()
        ctx["nav_event"] = latest
        ctx["is_admin"] = user.is_admin
    return ctx
