from django.contrib import admin

from .models import LoadPosting, RecentSearch, TruckPosting


@admin.register(LoadPosting)
class LoadPostingAdmin(admin.ModelAdmin):
    list_display = ("__str__", "company_name", "pickup_date", "rate", "status", "posted_at")
    list_filter = ("status", "equipment", "origin_state")


@admin.register(TruckPosting)
class TruckPostingAdmin(admin.ModelAdmin):
    list_display = ("__str__", "equipment", "available_from", "available_to", "active")
    list_filter = ("active", "equipment")


admin.site.register(RecentSearch)
