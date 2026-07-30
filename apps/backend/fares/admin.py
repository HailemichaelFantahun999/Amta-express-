from django.contrib import admin

from fares.models import FareSettings


@admin.register(FareSettings)
class FareSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "base_fare",
        "km_reference",
        "per_km_rate",
        "kg_base",
        "kg_reference",
        "per_kg_rate",
        "per_minute_rate",
        "bidding_radius_km",
        "updated_at",
    )
