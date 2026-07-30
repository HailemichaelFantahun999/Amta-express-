from django.conf import settings
from django.db import models


class Vehicle(models.Model):
    class VehicleType(models.TextChoices):
        DRY_VAN = "dry_van", "Dry Van"
        REEFER = "reefer", "Reefer"
        BOX_TRUCK = "box_truck", "Box Truck"
        FLATBED = "flatbed", "Flatbed"
        SPRINTER = "sprinter", "Sprinter"

    class FuelType(models.TextChoices):
        DIESEL = "diesel", "Diesel"
        GASOLINE = "gasoline", "Gasoline"
        ELECTRIC = "electric", "Electric"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MAINTENANCE = "maintenance", "Maintenance"
        OFFLINE = "offline", "Offline"

    identifier = models.CharField(max_length=50, unique=True)
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices)
    fuel_type = models.CharField(
        max_length=20, choices=FuelType.choices, default=FuelType.DIESEL
    )
    license_plate = models.CharField(max_length=50, unique=True)
    image = models.TextField(blank=True)
    bolo_number = models.CharField(max_length=100, blank=True)
    last_service_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    fuel_level = models.PositiveIntegerField(default=100)
    assigned_driver = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="assigned_vehicle",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    category = models.ForeignKey(
        "VehicleCategory",
        related_name="vehicles",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.identifier


class VehicleCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    bidding = models.BooleanField(default=False)
    base_fare = models.DecimalField(max_digits=10, decimal_places=2, default=50)
    km_reference = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    per_km_rate = models.DecimalField(max_digits=10, decimal_places=2, default=15)
    kg_base = models.DecimalField(max_digits=10, decimal_places=2, default=2000)
    kg_reference = models.DecimalField(max_digits=10, decimal_places=2, default=200)
    per_kg_rate = models.DecimalField(max_digits=10, decimal_places=2, default=5)
    per_minute_rate = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    bidding_radius_km = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vehicle Category"
        verbose_name_plural = "Vehicle Categories"

    def save(self, *args, **kwargs):
        from features.fares.fare_utils import sync_category_rates

        sync_category_rates(self)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
