from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import RegistrationForm, UserRoleForm
from .models import User
from .permissions import AdminMixin


class RegisterView(CreateView):
    form_class = RegistrationForm
    template_name = "registration/register.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, "Welcome! Your dispatcher account is ready.")
        return redirect("home")


class UserListView(AdminMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    ordering = ["username"]


class UserUpdateView(AdminMixin, UpdateView):
    model = User
    form_class = UserRoleForm
    template_name = "form.html"
    success_url = reverse_lazy("user_list")
    extra_context = {"title": "Edit user"}

    def form_valid(self, form):
        if form.instance == self.request.user and not form.cleaned_data["is_active"]:
            form.add_error("is_active", "You cannot deactivate your own account.")
            return self.form_invalid(form)
        messages.success(self.request, "User updated.")
        return super().form_valid(form)
