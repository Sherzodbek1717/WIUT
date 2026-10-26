from django.contrib import admin

from .models import Assignment, Broker, Driver, Load, ProofOfDelivery, Truck

admin.site.register(Broker)
admin.site.register(Driver)
admin.site.register(Truck)
admin.site.register(ProofOfDelivery)


@admin.register(Load)
class LoadAdmin(admin.ModelAdmin):
    list_display = ("__str__", "broker", "status", "pickup_at", "rate")
    list_filter = ("status", "broker")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("load", "driver", "truck", "assigned_at", "active")
