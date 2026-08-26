import time

from django.core.cache import cache
from django.http import JsonResponse


class BruteForceMiddleware:
    LOGIN_ATTEMPT_KEY = "bf_login_{ip}"
    MAX_ATTEMPTS = 5
    WINDOW_SECONDS = 900  # 15 minutes

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/login/" and request.method == "POST":
            ip = self._get_ip(request)
            key = self.LOGIN_ATTEMPT_KEY.format(ip=ip)
            data = cache.get(key)

            if data and data.get("locked_until", 0) > time.time():
                remaining = int(data["locked_until"] - time.time())
                return JsonResponse(
                    {"ok": False, "error": f"Too many failed attempts. Try again in {remaining}s."},
                    status=429,
                )

        response = self.get_response(request)

        if request.path == "/login/" and request.method == "POST":
            ip = self._get_ip(request)
            key = self.LOGIN_ATTEMPT_KEY.format(ip=ip)
            data = cache.get(key) or {"attempts": 0, "locked_until": 0}

            from django.contrib import messages as django_messages

            has_error = any(
                m.level_tag == "error"
                for m in django_messages.get_messages(request)
                if hasattr(m, "level_tag")
            )

            if has_error:
                data["attempts"] = data.get("attempts", 0) + 1
                if data["attempts"] >= self.MAX_ATTEMPTS:
                    data["locked_until"] = time.time() + self.WINDOW_SECONDS
                cache.set(key, data, self.WINDOW_SECONDS + 60)
            elif response.status_code in (302, 303):
                cache.delete(key)

        return response

    def _get_ip(self, request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "0.0.0.0")
