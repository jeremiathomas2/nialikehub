from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import models
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
    if request.method == "POST":
        op = request.POST.get("op")
        if op == "remove_photo":
            request.user.profile_photo = None
            request.user.save(update_fields=["profile_photo"])
            audit(request, "profile_photo_removed", "users", request.user.pk)
            messages.success(request, "Profile photo removed.")
            return redirect("accounts:profile")
        if op == "upload_photo":
            photo = request.FILES.get("profile_photo")
            if photo:
                request.user.profile_photo = photo
                request.user.save(update_fields=["profile_photo"])
                audit(request, "profile_photo_uploaded", "users", request.user.pk)
                messages.success(request, "Profile photo updated.")
            return redirect("accounts:profile")

    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request, "profile_updated", "users", request.user.pk)
        messages.success(request, "Profile updated.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form, "active": "profile", "page_title": "My Profile"})


@admin_required
def user_management_view(request):
    status_order = [User.Status.PENDING, User.Status.APPROVED, User.Status.SUSPENDED]
    ordering = Case(
        *[When(status=s, then=pos) for pos, s in enumerate(status_order)],
        output_field=IntegerField(),
    )

    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "")
    rows = User.objects.all()
    if q:
        rows = rows.filter(models.Q(name__icontains=q) | models.Q(email__icontains=q))
    if status_filter in status_order:
        rows = rows.filter(status=status_filter)
    rows = rows.order_by(ordering, "-pk")

    if request.method == "POST":
        target_id = int(request.POST.get("id", 0))
        op = request.POST.get("op", "")
        target = User.objects.filter(pk=target_id).first()
        if not target:
            messages.error(request, "User not found.")
            return redirect("accounts:user_management")

        if target.pk == request.user.pk and op in ("delete", "role"):
            messages.error(request, "You cannot perform this action on your own account.")
            return redirect("accounts:user_management")

        if op == "edit":
            new_name = request.POST.get("name", "").strip()[:120]
            new_email = request.POST.get("email", "").strip().lower()[:190]
            new_phone = request.POST.get("phone", "").strip()[:30] or None
            new_role = request.POST.get("role", target.role)
            new_status = request.POST.get("status", target.status)
            if not new_name or not new_email:
                messages.error(request, "Name and email are required.")
                return redirect("accounts:user_management")
            if new_role not in (User.Role.ADMIN, User.Role.USER):
                new_role = User.Role.USER
            if new_status not in status_order:
                new_status = target.status
            if new_email != target.email and User.objects.filter(email=new_email).exclude(pk=target.pk).exists():
                messages.error(request, "That email is already in use.")
                return redirect("accounts:user_management")
            target.name = new_name
            target.email = new_email
            target.phone = new_phone
            target.role = new_role
            target.status = new_status
            target.is_approved = new_status == User.Status.APPROVED
            if new_role == User.Role.ADMIN:
                target.is_staff = True
                target.is_approved = True
                target.status = User.Status.APPROVED
            target.updated_at = timezone.now()
            target.save()
            audit(request, "user_updated", "users", target.pk, {"name": target.name, "email": target.email, "role": target.role, "status": target.status})
            messages.success(request, f"{target.name or target.email} updated.")

        elif op == "status":
            new_status = request.POST.get("status", User.Status.PENDING)
            if new_status not in status_order:
                new_status = User.Status.PENDING
            target.status = new_status
            target.is_approved = new_status == User.Status.APPROVED
            target.updated_at = timezone.now()
            target.save(update_fields=["status", "is_approved", "updated_at"])
            audit(request, "user_status_changed", "users", target.pk, {"status": new_status})
            messages.success(request, f"{target.name or target.email} status updated to {new_status}.")

        elif op == "role":
            new_role = request.POST.get("role", User.Role.USER)
            if new_role not in (User.Role.ADMIN, User.Role.USER):
                new_role = User.Role.USER
            target.role = new_role
            target.updated_at = timezone.now()
            save_fields = ["role", "updated_at"]
            if new_role == User.Role.ADMIN:
                target.is_staff = True
                target.is_approved = True
                target.status = User.Status.APPROVED
                save_fields += ["is_staff", "is_approved", "status"]
            target.save(update_fields=save_fields)
            audit(request, "user_role_changed", "users", target.pk, {"role": new_role})
            messages.success(request, f"{target.name or target.email} role changed to {new_role}.")

        elif op == "toggle_active":
            target.is_active = not target.is_active
            target.updated_at = timezone.now()
            target.save(update_fields=["is_active", "updated_at"])
            state = "activated" if target.is_active else "deactivated"
            audit(request, "user_toggled_active", "users", target.pk, {"is_active": target.is_active})
            messages.success(request, f"{target.name or target.email} {state}.")

        elif op == "delete":
            confirm = request.POST.get("confirm_delete", "")
            if confirm != target.email:
                messages.error(request, "Email confirmation did not match. Deletion cancelled.")
                return redirect("accounts:user_management")
            name = target.name or target.email
            audit(request, "user_deleted", "users", target.pk, {"email": target.email, "name": name})
            target.delete()
            messages.success(request, f"{name} and all associated data have been deleted.")
            return redirect("accounts:user_management")

        return redirect("accounts:user_management")

    counts = {
        "total": User.objects.count(),
        "pending": User.objects.filter(status=User.Status.PENDING).count(),
        "approved": User.objects.filter(status=User.Status.APPROVED).count(),
        "suspended": User.objects.filter(status=User.Status.SUSPENDED).count(),
    }
    return render(
        request,
        "accounts/user_management.html",
        {
            "rows": rows,
            "counts": counts,
            "q": q,
            "status_filter": status_filter,
            "statuses": [s for s in User.Status],
            "roles": [r for r in User.Role],
            "active": "users",
            "page_title": "User Management",
            "page_eyebrow": "Administration",
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
