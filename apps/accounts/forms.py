from django import forms
from django.contrib.auth.password_validation import validate_password
from .models import User


class RegisterForm(forms.Form):
    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={"class": "neu-input", "placeholder": "Full name", "autocomplete": "name"}),
    )
    email = forms.EmailField(
        max_length=190,
        widget=forms.EmailInput(
            attrs={"class": "neu-input", "placeholder": "you@example.com", "autocomplete": "email"}
        ),
    )
    phone = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={"class": "neu-input", "placeholder": "07xxxxxxxx", "autocomplete": "tel"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "neu-input", "placeholder": "At least 8 characters", "autocomplete": "new-password"}
        )
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "neu-input", "placeholder": "Repeat password", "autocomplete": "new-password"}
        )
    )

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("password_confirm")
        if not password or len(password) < 8:
            self.add_error("password", "Password must be at least 8 characters.")
        elif password != confirm:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("That email is already registered.")
        return email


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "neu-input",
                "autofocus": True,
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "neu-input", "placeholder": "Your password", "autocomplete": "current-password"}
        )
    )


class ProfileForm(forms.ModelForm):
    email = forms.EmailField(
        disabled=True,
        label="Email (login)",
        help_text="Email cannot be changed.",
        widget=forms.EmailInput(attrs={"class": "neu-input"}),
    )
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "neu-input",
                "autocomplete": "new-password",
                "placeholder": "Enter a new password",
            }
        ),
        help_text="Leave blank to keep current password.",
    )

    class Meta:
        model = User
        fields = ["name", "email", "phone", "profile_photo"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "neu-input", "autocomplete": "name", "placeholder": "Your full name"}
            ),
            "phone": forms.TextInput(
                attrs={"class": "neu-input", "autocomplete": "tel", "placeholder": "07xxxxxxxx"}
            ),
            "profile_photo": forms.ClearableFileInput(
                attrs={"class": "neu-input", "accept": "image/*", "id": "profilePhotoInput"}
            ),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        new_password = self.cleaned_data.get("new_password")
        if new_password:
            user.set_password(new_password)
        if commit:
            user.save()
        return user


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "neu-input",
                "autofocus": True,
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        )
    )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if not User.objects.filter(email=email, is_active=True).exists():
            raise forms.ValidationError("No active account found with this email.")
        return email


class SetNewPasswordForm(forms.Form):
    new_password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "neu-input",
                "autocomplete": "new-password",
                "placeholder": "At least 8 characters",
            }
        )
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "neu-input",
                "autocomplete": "new-password",
                "placeholder": "Repeat password",
            }
        )
    )

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("new_password")
        confirm = cleaned.get("confirm_password")
        if password and len(password) < 8:
            self.add_error("new_password", "Password must be at least 8 characters.")
        elif password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned
