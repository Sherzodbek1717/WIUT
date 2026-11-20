"""Role checks shared by every app's views."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class OperationsEditMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Dispatcher or admin: may create and change operational records."""

    def test_func(self):
        return self.request.user.can_edit_operations


class AnalyticsMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Manager or admin: may view the dashboard and reports."""

    def test_func(self):
        return self.request.user.can_view_analytics


class AdminMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Admin only: may manage user accounts and company settings."""

    def test_func(self):
        return self.request.user.is_platform_admin


class TmsMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Carrier staff (not brokers): may view the TMS pages."""

    def test_func(self):
        return self.request.user.can_use_tms


def tms_required(view):
    """Function-view version of TmsMixin."""
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.can_use_tms:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
