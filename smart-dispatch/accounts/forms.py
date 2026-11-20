from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegistrationForm(UserCreationForm):
    """Self-registration as a carrier dispatcher or a broker. Managers and admins are set by an admin."""

    role = forms.ChoiceField(
        label="I am a",
        choices=[(User.Role.DISPATCHER, "Dispatcher / carrier (search loads)"), (User.Role.BROKER, "Broker (post loads)")],
        widget=forms.RadioSelect,
        initial=User.Role.DISPATCHER,
    )

    class Meta:
        model = User
        fields = ("role", "username", "first_name", "last_name", "email", "company_name", "phone")


class UserRoleForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "company_name", "phone", "role", "is_active")
