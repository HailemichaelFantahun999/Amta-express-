from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    class Type(models.TextChoices):
        GENERAL = "general", "General"
        BIDDING_OPEN = "bidding_open", "Bidding open"
        BID_RECEIVED = "bid_received", "Bid received"
        BID_UPDATED = "bid_updated", "Bid updated"
        BID_COUNTER = "bid_counter", "Counter offer"
        COUNTER_ACCEPTED = "counter_accepted", "Counter accepted"
        COUNTER_DECLINED = "counter_declined", "Counter declined"
        BID_AWARDED = "bid_awarded", "Bid awarded"
        BID_LOST = "bid_lost", "Bid not selected"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="notifications", on_delete=models.CASCADE
    )
    delivery = models.ForeignKey(
        "deliveries.Delivery",
        related_name="notifications",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    bid_request = models.ForeignKey(
        "bidding.BidRequest",
        related_name="notifications",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    bid = models.ForeignKey(
        "bidding.Bid",
        related_name="notifications",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    notification_type = models.CharField(
        max_length=30, choices=Type.choices, default=Type.GENERAL
    )
    link_path = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=120)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def mark_read(self):
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])
