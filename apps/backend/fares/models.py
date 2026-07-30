from django.db import models


class FareSettings(models.Model):
    base_fare = models.DecimalField(max_digits=10, decimal_places=2, default=50)
    km_reference = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    per_km_rate = models.DecimalField(max_digits=10, decimal_places=2, default=15)
    kg_base = models.DecimalField(max_digits=10, decimal_places=2, default=2000)
    kg_reference = models.DecimalField(max_digits=10, decimal_places=2, default=200)
    per_kg_rate = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    per_minute_rate = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    bidding_radius_km = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Fare settings"

    def save(self, *args, **kwargs):
        from fares.fare_utils import sync_fare_settings_rates

        sync_fare_settings_rates(self)
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        settings_obj, _ = cls.objects.get_or_create(
            id=1,
            defaults={
                "base_fare": 50,
                "km_reference": 100,
                "per_km_rate": 15,
                "kg_base": 2000,
                "kg_reference": 200,
                "per_kg_rate": 10,
                "per_minute_rate": 1,
                "bidding_radius_km": 5,
            },
        )
        return settings_obj
