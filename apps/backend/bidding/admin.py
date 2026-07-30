from django.contrib import admin

from bidding.models import Bid, BidRequest


@admin.register(BidRequest)
class BidRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "delivery", "category", "status", "radius_km", "created_at")
    list_filter = ("status", "category")
    filter_horizontal = ("eligible_drivers",)


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "bid_request",
        "driver",
        "amount",
        "distance_km",
        "weight_kg",
        "status",
        "created_at",
    )
    list_filter = ("status",)
