from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Platform user. The role decides which pages the user can reach."""

    class Role(models.TextChoices):
        DISPATCHER = "dispatcher", "Dispatcher"
        BROKER = "broker", "Broker"
        MANAGER = "manager", "Manager"
        ADMIN = "admin", "Admin"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DISPATCHER)
    company_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    @property
    def is_dispatcher(self):
        return self.role == self.Role.DISPATCHER

    @property
    def is_broker(self):
        return self.role == self.Role.BROKER

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_platform_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def can_edit_operations(self):
        """Dispatchers and admins change loads, drivers and trucks; managers only view."""
        return self.is_dispatcher or self.is_platform_admin

    @property
    def can_use_tms(self):
        """The dispatch side (loads, drivers, trucks, board) is for carriers, not brokers."""
        return not self.is_broker

    @property
    def can_search_loads(self):
        return self.is_dispatcher or self.is_platform_admin

    @property
    def can_post_loads(self):
        return self.is_broker or self.is_platform_admin

    @property
    def can_view_analytics(self):
        return self.is_manager or self.is_platform_admin

    def __str__(self):
        return self.get_full_name() or self.username
