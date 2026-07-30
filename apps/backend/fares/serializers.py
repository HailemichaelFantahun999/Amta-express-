from rest_framework import serializers

from fares.models import FareSettings


class FareSettingsSerializer(serializers.ModelSerializer):
    km_base = serializers.DecimalField(
        source="base_fare", max_digits=10, decimal_places=2
    )

    class Meta:
        model = FareSettings
        fields = [
            "km_base",
            "km_reference",
            "per_km_rate",
            "kg_base",
            "kg_reference",
            "per_kg_rate",
            "per_minute_rate",
            "bidding_radius_km",
            "updated_at",
        ]
        read_only_fields = ["per_km_rate", "per_kg_rate", "updated_at"]


class FareRuleSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=100)
    min_distance = serializers.DecimalField(max_digits=10, decimal_places=2)
    max_distance = serializers.DecimalField(max_digits=10, decimal_places=2)
    rate = serializers.DecimalField(max_digits=10, decimal_places=2)
    active = serializers.BooleanField(default=True)
