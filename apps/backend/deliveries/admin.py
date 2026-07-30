from django.contrib import admin

from deliveries.models import Delivery, DeliveryEvent


class DeliveryEventInline(admin.TabularInline):
    model = DeliveryEvent
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "customer",
        "requested_category",
        "payment_method",
        "assigned_driver",
        "status",
        "pickup_location",
        "delivery_location",
        "pickup_datetime",
    )
    search_fields = (
        "public_id",
        "pickup_location",
        "delivery_location",
        "customer__email",
        "assigned_driver__email",
    )
    list_filter = ("status", "request_source", "payment_method", "pickup_datetime")
    inlines = [DeliveryEventInline]
