from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db.models import Case, IntegerField, When
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_POST

from apps.core.services import audit

from .decorators import admin_required
from .forms import LoginForm, ProfileForm, RegisterForm, PasswordResetRequestForm, SetNewPasswordForm
from .models import User
from .tokens import password_reset_token, email_verify_token


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
        elif not user.email_verified:
            messages.warning(request, "Please verify your email before signing in.")
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
            email_verified=False,
        )
        uid = urlsafe_base64_encode(str(user.pk).encode())
        token = email_verify_token.make_token(user)
        verify_url = f"/verify-email/{uid}/{token}/"
        audit(request, "user_registered", "users", user.pk, {"email": user.email})
        messages.success(request, f"Account created. Verify your email: {verify_url}")
        return redirect("accounts:login")
    return render(request, "auth/register.html", {"form": form, "page_title": "Create account"})


@require_POST
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


@admin_required
def approvals_view(request):
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


def password_reset_request_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        user = User.objects.get(email=email, is_active=True)
        uid = urlsafe_base64_encode(str(user.pk).encode())
        token = password_reset_token.make_token(user)
        reset_url = f"/password-reset/{uid}/{token}/"
        audit(request, "password_reset_requested", "users", user.pk, {"email": email})
        messages.success(request, f"Password reset link: {reset_url}")
        return redirect("accounts:password_reset_done")
    return render(request, "auth/password_reset.html", {"form": form, "page_title": "Reset Password"})


def password_reset_done_view(request):
    return render(request, "auth/password_reset_done.html", {"page_title": "Check Your Email"})


def password_reset_confirm_view(request, uidb64, token):
    try:
        uid = int(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid, is_active=True)
    except (ValueError, TypeError, User.DoesNotExist):
        user = None

    if not user or not password_reset_token.check_token(user, token):
        messages.error(request, "Password reset link is invalid or has expired.")
        return redirect("accounts:login")

    form = SetNewPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user.set_password(form.cleaned_data["new_password"])
        user.save(update_fields=["password"])
        audit(request, "password_reset_completed", "users", user.pk)
        messages.success(request, "Password has been reset. You can now sign in.")
        return redirect("accounts:login")
    return render(request, "auth/password_reset_confirm.html", {"form": form, "page_title": "Set New Password"})


def verify_email_view(request, uidb64, token):
    try:
        uid = int(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid, is_active=True)
    except (ValueError, TypeError, User.DoesNotExist):
        user = None

    if not user or not email_verify_token.check_token(user, token):
        messages.error(request, "Verification link is invalid or has expired.")
        return redirect("accounts:login")

    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        audit(request, "email_verified", "users", user.pk)
    messages.success(request, "Email verified successfully. You can now sign in.")
    return render(request, "auth/verify_email.html", {"page_title": "Email Verified"})
