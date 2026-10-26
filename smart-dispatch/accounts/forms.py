from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegistrationForm(UserCreationForm):
    """Self-registration. New accounts are dispatchers; an admin can change the role."""

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")


class UserRoleForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "role", "is_active")
