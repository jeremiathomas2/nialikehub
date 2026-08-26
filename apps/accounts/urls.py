from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("approvals/", views.approvals_view, name="approvals"),
    path("password-reset/", views.password_reset_request_view, name="password_reset"),
    path("password-reset/done/", views.password_reset_done_view, name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", views.password_reset_confirm_view, name="password_reset_confirm"),
    path("verify-email/<uidb64>/<token>/", views.verify_email_view, name="verify_email"),
]
