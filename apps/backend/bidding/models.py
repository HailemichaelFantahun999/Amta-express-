from django.conf import settings
from django.db import models

from deliveries.models import Delivery
from vehicles.models import VehicleCategory


class BidRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        AWARDED = "awarded", "Awarded"
        CANCELLED = "cancelled", "Cancelled"

    delivery = models.ForeignKey(
        Delivery, related_name="bid_requests", on_delete=models.CASCADE
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="bid_requests", on_delete=models.CASCADE
    )
    category = models.ForeignKey(
        VehicleCategory,
        related_name="bid_requests",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    radius_km = models.DecimalField(max_digits=5, decimal_places=2, default=5.00)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    winning_bid = models.ForeignKey(
        "Bid",
        related_name="won_bid_requests",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    eligible_drivers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="eligible_bid_requests",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Bidding for {self.delivery.public_id}"


class Bid(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    class BidMethod(models.TextChoices):
        KM = "km", "Per KM"
        KG = "kg", "Per KG"

    bid_request = models.ForeignKey(
        BidRequest, related_name="bids", on_delete=models.CASCADE
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="bids", on_delete=models.CASCADE
    )
    bid_method = models.CharField(
        max_length=5, choices=BidMethod.choices, default=BidMethod.KM
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    message = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    counter_unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    counter_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    counter_message = models.TextField(blank=True)
    counter_status = models.CharField(
        max_length=20,
        choices=[
            ("none", "None"),
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("declined", "Declined"),
        ],
        default="none",
    )
    counter_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["amount", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["bid_request", "driver"], name="unique_bid_per_driver_request"
            ),
        ]

    def __str__(self):
        return f"Bid {self.amount} by {self.driver_id} for {self.bid_request_id}"


class BidNegotiation(models.Model):
    class Party(models.TextChoices):
        DRIVER = "driver", "Driver"
        CUSTOMER = "customer", "Customer"

    bid_request = models.ForeignKey(
        BidRequest, related_name="negotiations", on_delete=models.CASCADE
    )
    bid = models.ForeignKey(Bid, related_name="negotiations", on_delete=models.CASCADE)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="bid_negotiations",
        on_delete=models.CASCADE,
    )
    party = models.CharField(max_length=20, choices=Party.choices)
    bid_method = models.CharField(
        max_length=5, choices=Bid.BidMethod.choices, default=Bid.BidMethod.KM
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.party} offer {self.amount} on bid {self.bid_id}"
