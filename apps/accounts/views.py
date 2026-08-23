import time

from django.db.models import Case, IntegerField, When
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.core.services import audit

from .forms import LoginForm, ProfileForm, RegisterForm
from .models import User


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower()
        password = form.cleaned_data["password"]
        user = authenticate(request, username=email, password=password)
        if not user:
            messages.error(request, "Email or password is incorrect.")
        elif user.status == User.Status.PENDING:
            messages.warning(request, "Account is awaiting admin approval.")
        elif user.status == User.Status.SUSPENDED:
            messages.error(request, "Your account is suspended.")
        else:
            auth_login(request, user)
            audit(request, "login", "users", user.pk)
            return redirect("core:dashboard")
    return render(request, "auth/login.html", {"form": form, "page_title": "Login"})


def register_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
            name=form.cleaned_data["name"],
            phone=form.cleaned_data.get("phone") or None,
            role=User.Role.USER,
            status=User.Status.PENDING,
            is_approved=False,
        )
        audit(request, "user_registered", "users", user.pk, {"email": user.email})
        messages.success(request, "Account created. An administrator must approve it before login.")
        return redirect("accounts:login")
    return render(request, "auth/register.html", {"form": form, "page_title": "Create account"})


def logout_view(request):
    auth_logout(request)
    return redirect("accounts:login")


@login_required
def profile_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request, "profile_updated", "users", request.user.pk)
        messages.success(request, "Profile updated.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form, "active": "profile", "page_title": "My Profile"})


@login_required
def approvals_view(request):
    if not request.user.is_admin:
        return HttpResponseForbidden("Forbidden")
    status_order = [User.Status.PENDING, User.Status.APPROVED, User.Status.SUSPENDED]
    ordering = Case(
        *[When(status=s, then=pos) for pos, s in enumerate(status_order)],
        output_field=IntegerField(),
    )
    rows = User.objects.filter(role=User.Role.USER).order_by(ordering, "-pk")

    if request.method == "POST":
        target_id = int(request.POST.get("id", 0))
        new_status = request.POST.get("status", User.Status.PENDING)
        if new_status not in status_order:
            new_status = User.Status.PENDING
        updated = User.objects.filter(pk=target_id, role=User.Role.USER).update(
            status=new_status,
            is_approved=(new_status == User.Status.APPROVED),
            updated_at=timezone.now(),
        )
        if updated:
            audit(request, "user_status_changed", "users", target_id, {"status": new_status})
            messages.success(request, "User status updated.")
        return redirect("accounts:approvals")

    pending_count = rows.filter(status=User.Status.PENDING).count()
    return render(
        request,
        "accounts/approvals.html",
        {
            "rows": rows,
            "pending_count": pending_count,
            "statuses": [s for s in User.Status],
            "active": "users",
            "page_title": "User Approvals",
        },
    )
