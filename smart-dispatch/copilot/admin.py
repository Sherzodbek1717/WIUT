from django.contrib import admin

from .models import CallLog, EmailMessage


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "to_email", "user", "status", "ai_written", "sent_at")
    list_filter = ("status", "ai_written")


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ("broker", "outcome", "rate_quoted", "user", "called_at")
    list_filter = ("outcome",)
