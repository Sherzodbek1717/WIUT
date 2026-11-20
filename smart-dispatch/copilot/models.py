from django.conf import settings
from django.db import models


class EmailMessage(models.Model):
    """An email a dispatcher sent to a broker from the app (the Mailbox)."""

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_emails")
    broker = models.ForeignKey("dispatch.Broker", on_delete=models.SET_NULL, null=True, blank=True, related_name="emails")
    posting = models.ForeignKey("loadboard.LoadPosting", on_delete=models.SET_NULL, null=True, blank=True, related_name="emails")
    to_email = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    ai_written = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENT)
    error = models.CharField(max_length=250, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.subject} → {self.to_email}"


class CallLog(models.Model):
    """The result of a call to a broker, logged from the Call Assistant."""

    class Outcome(models.TextChoices):
        BOOKED = "booked", "Booked"
        QUOTED = "quoted", "Got a rate"
        NEGOTIATING = "negotiating", "Negotiating / call back"
        COVERED = "covered", "Load already covered"
        NO_ANSWER = "no_answer", "No answer / voicemail"
        DECLINED = "declined", "Rate too low – passed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calls")
    broker = models.ForeignKey("dispatch.Broker", on_delete=models.SET_NULL, null=True, blank=True, related_name="calls")
    posting = models.ForeignKey("loadboard.LoadPosting", on_delete=models.SET_NULL, null=True, blank=True, related_name="calls")
    phone = models.CharField(max_length=30, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    rate_quoted = models.DecimalField("rate quoted ($)", max_digits=9, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    called_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-called_at"]

    def __str__(self):
        return f"{self.broker or self.phone}: {self.get_outcome_display()}"
