from django.conf import settings
from django.db import models

from vehicles.models import Vehicle, VehicleCategory


class Delivery(models.Model):
    class RequestSource(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        DISPATCHER = "dispatcher", "Dispatcher"
        ADMIN = "admin", "Admin"

    class Status(models.TextChoices):
        PENDING_ASSIGNMENT = "pending_assignment", "Pending Assignment"
        PENDING_DRIVER_RESPONSE = "pending_driver_response", "Pending Driver Response"
        ASSIGNED = "assigned", "Assigned"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        IN_TRANSIT = "in_transit", "In Transit"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    public_id = models.CharField(max_length=20, unique=True, blank=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="customer_deliveries",
        on_delete=models.CASCADE,
    )
    dispatcher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="dispatched_deliveries",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    assigned_driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="driver_deliveries",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    assigned_vehicle = models.ForeignKey(
        Vehicle,
        related_name="deliveries",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    pickup_location = models.CharField(max_length=255)
    delivery_location = models.CharField(max_length=255)
    pickup_datetime = models.DateTimeField()
    delivery_window = models.CharField(max_length=100, blank=True)
    package_details = models.CharField(max_length=255)
    special_instructions = models.TextField(blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    request_source = models.CharField(
        max_length=20, choices=RequestSource.choices, default=RequestSource.CUSTOMER
    )
    status = models.CharField(
        max_length=40, choices=Status.choices, default=Status.PENDING_ASSIGNMENT
    )
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    package_weight_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_drive_minutes = models.PositiveIntegerField(default=0)
    fare = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    route_geometry = models.JSONField(null=True, blank=True)
    requested_vehicle_type = models.CharField(max_length=20, blank=True, default="")
    requested_category = models.ForeignKey(
        VehicleCategory,
        related_name="requested_deliveries",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    payment_method = models.CharField(
        max_length=20,
        choices=[
            ("mixed", "Mixed distance + time"),
            ("distance", "Distance only"),
            ("time", "Time only"),
        ],
        default="mixed",
    )
    latest_note = models.CharField(max_length=255, blank=True)
    decline_reason = models.CharField(max_length=255, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.public_id:
            prefix = "D"
            count = Delivery.objects.count()
            next_num = 1001 + count
            while Delivery.objects.filter(public_id=f"{prefix}-{next_num}").exists():
                next_num += 1
            self.public_id = f"{prefix}-{next_num}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.public_id


class DriverRating(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="given_ratings", on_delete=models.CASCADE
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="received_ratings",
        on_delete=models.CASCADE,
    )
    delivery = models.ForeignKey(
        Delivery, related_name="ratings", on_delete=models.CASCADE
    )
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["customer", "delivery"]

    def __str__(self):
        return f"{self.customer.email} rated {self.driver.email} - {self.rating} stars"


class DeliveryEvent(models.Model):
    class EventType(models.TextChoices):
        CREATED = "created", "Created"
        ASSIGNED = "assigned", "Assigned"
        REASSIGNED = "reassigned", "Reassigned"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        REACHED_PICKUP = "reached_pickup", "Reached Pickup"
        STARTED = "started", "Started"
        DELIVERED = "delivered", "Delivered"
        NOTE = "note", "Note"

    delivery = models.ForeignKey(
        Delivery, related_name="events", on_delete=models.CASCADE
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="delivery_events",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
