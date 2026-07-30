from django.contrib import admin

from vehicles.models import Vehicle, VehicleCategory


class VehicleInline(admin.TabularInline):
    model = Vehicle
    fields = ("identifier", "assigned_driver", "status", "license_plate")
    extra = 0
    show_change_link = True


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        "identifier",
        "vehicle_type",
        "category",
        "status",
        "license_plate",
        "assigned_driver",
        "fuel_level",
    )
    search_fields = ("identifier", "license_plate")
    list_filter = ("vehicle_type", "status", "fuel_type", "category")


@admin.register(VehicleCategory)
class VehicleCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "bidding",
        "base_fare",
        "km_reference",
        "per_km_rate",
        "kg_base",
        "kg_reference",
        "per_kg_rate",
        "bidding_radius_km",
        "per_minute_rate",
        "created_at",
        "updated_at",
    )
    list_filter = ("bidding",)
    search_fields = ("name",)
    inlines = [VehicleInline]
