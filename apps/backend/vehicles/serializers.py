from rest_framework import serializers

from features.accounts.serializers import UserSerializer
from vehicles.models import Vehicle, VehicleCategory


class VehicleCategorySerializer(serializers.ModelSerializer):
    km_base = serializers.DecimalField(
        source="base_fare", max_digits=10, decimal_places=2, required=False
    )
    km_reference = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )
    kg_base = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    kg_reference = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )
    per_minute_rate = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )
    bidding_radius_km = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True
    )

    class Meta:
        model = VehicleCategory
        fields = [
            "id",
            "name",
            "bidding",
            "km_base",
            "km_reference",
            "per_km_rate",
            "kg_base",
            "kg_reference",
            "per_kg_rate",
            "per_minute_rate",
            "bidding_radius_km",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["per_km_rate", "per_kg_rate", "created_at", "updated_at"]


class VehicleSerializer(serializers.ModelSerializer):
    assigned_driver = UserSerializer(read_only=True)
    assigned_driver_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=VehicleCategory.objects.all(),
        source="category",
        required=False,
        allow_null=True,
    )
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_bidding = serializers.BooleanField(
        source="category.bidding", read_only=True
    )
    vehicle_type_label = serializers.CharField(
        source="get_vehicle_type_display", read_only=True
    )
    fuel_type_label = serializers.CharField(
        source="get_fuel_type_display", read_only=True
    )

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "identifier",
            "vehicle_type",
            "vehicle_type_label",
            "fuel_type",
            "fuel_type_label",
            "license_plate",
            "image",
            "bolo_number",
            "last_service_date",
            "status",
            "fuel_level",
            "assigned_driver",
            "assigned_driver_id",
            "category_id",
            "category_name",
            "category_bidding",
        ]

    def create(self, validated_data):
        assigned_driver_id = validated_data.pop("assigned_driver_id", None)
        vehicle = Vehicle.objects.create(**validated_data)
        if assigned_driver_id:
            vehicle.assigned_driver_id = assigned_driver_id
            vehicle.save(update_fields=["assigned_driver"])
        return vehicle
