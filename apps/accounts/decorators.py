from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def admin_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_admin:
            return HttpResponseForbidden("Forbidden")
        return view_func(request, *args, **kwargs)
    return _wrapped


def get_event_for(user, event_id):
    from apps.events.models import Event
    qs = Event.objects.all() if user.is_admin else Event.objects.filter(user=user)
    return qs.filter(pk=event_id).first()


def visible_events(user):
    from apps.events.models import Event
    return Event.objects.all() if user.is_admin else Event.objects.filter(user=user)
