"""Role checks shared by every app's views."""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


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
