from rest_framework import serializers

from bidding.models import Bid, BidNegotiation, BidRequest


class BidNegotiationSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = BidNegotiation
        fields = [
            "id",
            "party",
            "bid_method",
            "unit_price",
            "amount",
            "message",
            "actor_name",
            "created_at",
        ]

    def get_actor_name(self, obj):
        return obj.actor.get_full_name().strip() or obj.actor.email


class BidSerializer(serializers.ModelSerializer):
    driver_id = serializers.IntegerField(source="driver.id", read_only=True)
    driver_name = serializers.SerializerMethodField()
    driver_email = serializers.EmailField(source="driver.email", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Bid
        fields = [
            "id",
            "bid_request",
            "driver",
            "driver_id",
            "driver_name",
            "driver_email",
            "bid_method",
            "unit_price",
            "distance_km",
            "weight_kg",
            "amount",
            "message",
            "status",
            "status_label",
            "counter_unit_price",
            "counter_amount",
            "counter_message",
            "counter_status",
            "counter_at",
            "negotiations",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
            "driver",
            "amount",
            "status",
            "status_label",
            "counter_status",
            "counter_at",
            "negotiations",
        ]

    negotiations = BidNegotiationSerializer(many=True, read_only=True)

    def get_driver_name(self, obj):
        return obj.driver.get_full_name().strip() or obj.driver.email


class BidCreateSerializer(serializers.Serializer):
    bid_request = serializers.PrimaryKeyRelatedField(
        queryset=BidRequest.objects.filter(status=BidRequest.Status.OPEN)
    )
    bid_method = serializers.ChoiceField(
        choices=[("km", "Per KM"), ("kg", "Per KG")], default="km"
    )
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    message = serializers.CharField(required=False, allow_blank=True, default="")


class BidCounterSerializer(serializers.Serializer):
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    message = serializers.CharField(required=False, allow_blank=True, default="")


class BidRequestSerializer(serializers.ModelSerializer):
    delivery_id = serializers.IntegerField(source="delivery.id", read_only=True)
    delivery_public_id = serializers.CharField(
        source="delivery.public_id", read_only=True
    )
    pickup_location = serializers.CharField(
        source="delivery.pickup_location", read_only=True
    )
    delivery_location = serializers.CharField(
        source="delivery.delivery_location", read_only=True
    )
    route_distance_km = serializers.DecimalField(
        source="delivery.distance_km", max_digits=10, decimal_places=2, read_only=True
    )
    package_weight_kg = serializers.DecimalField(
        source="delivery.package_weight_kg",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    package_details = serializers.CharField(
        source="delivery.package_details", read_only=True
    )
    delivery_status = serializers.CharField(source="delivery.status", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_id = serializers.IntegerField(source="category.id", read_only=True)
    km_base = serializers.DecimalField(
        source="category.base_fare", max_digits=10, decimal_places=2, read_only=True
    )
    km_reference = serializers.DecimalField(
        source="category.km_reference", max_digits=10, decimal_places=2, read_only=True
    )
    per_km_rate = serializers.DecimalField(
        source="category.per_km_rate", max_digits=10, decimal_places=2, read_only=True
    )
    kg_base = serializers.DecimalField(
        source="category.kg_base", max_digits=10, decimal_places=2, read_only=True
    )
    kg_reference = serializers.DecimalField(
        source="category.kg_reference", max_digits=10, decimal_places=2, read_only=True
    )
    per_kg_rate = serializers.DecimalField(
        source="category.per_kg_rate", max_digits=10, decimal_places=2, read_only=True
    )
    base_fare = serializers.DecimalField(
        source="category.base_fare", max_digits=10, decimal_places=2, read_only=True
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    bids = BidSerializer(many=True, read_only=True)
    winning_bid_id = serializers.IntegerField(
        source="winning_bid.id", read_only=True, allow_null=True
    )

    class Meta:
        model = BidRequest
        fields = [
            "id",
            "delivery",
            "delivery_id",
            "delivery_public_id",
            "pickup_location",
            "delivery_location",
            "route_distance_km",
            "package_weight_kg",
            "package_details",
            "delivery_status",
            "customer",
            "category",
            "category_id",
            "category_name",
            "km_base",
            "km_reference",
            "base_fare",
            "per_km_rate",
            "kg_base",
            "kg_reference",
            "per_kg_rate",
            "radius_km",
            "status",
            "status_label",
            "winning_bid",
            "winning_bid_id",
            "created_at",
            "bids",
        ]
        read_only_fields = fields
