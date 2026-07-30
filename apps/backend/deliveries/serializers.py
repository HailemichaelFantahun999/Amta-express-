from decimal import Decimal

from rest_framework import serializers

from users.models import User
from features.accounts.serializers import UserSerializer
from fares.models import FareSettings
from fares.fare_utils import get_bidding_radius_km
from vehicles.models import VehicleCategory
from deliveries.models import Delivery, DeliveryEvent
from deliveries.utils import get_route_info


class DeliveryEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryEvent
        fields = ["id", "event_type", "message", "created_at", "actor_name"]

    def get_actor_name(self, obj):
        if not obj.actor:
            return "System"
        return obj.actor.get_full_name().strip() or obj.actor.email


class DeliverySerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    assigned_driver = UserSerializer(read_only=True)
    dispatcher = UserSerializer(read_only=True)
    assigned_vehicle = serializers.SerializerMethodField()
    selected_driver_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )
    requested_category_id = serializers.PrimaryKeyRelatedField(
        queryset=VehicleCategory.objects.all(),
        source="requested_category",
        required=False,
        allow_null=True,
    )
    requested_category_name = serializers.CharField(
        source="requested_category.name", read_only=True
    )
    requested_category_bidding = serializers.BooleanField(
        source="requested_category.bidding", read_only=True
    )
    payment_method = serializers.CharField(required=False, default="mixed")
    customer_phone = serializers.CharField(required=False, allow_blank=True)
    customer_latitude = serializers.FloatField(
        write_only=True, required=False, allow_null=True
    )
    customer_longitude = serializers.FloatField(
        write_only=True, required=False, allow_null=True
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    route = serializers.SerializerMethodField()
    timeline = DeliveryEventSerializer(source="events", many=True, read_only=True)
    rated = serializers.SerializerMethodField()

    class Meta:
        model = Delivery
        fields = [
            "id",
            "public_id",
            "customer",
            "dispatcher",
            "assigned_driver",
            "assigned_vehicle",
            "pickup_location",
            "delivery_location",
            "pickup_datetime",
            "delivery_window",
            "package_details",
            "special_instructions",
            "request_source",
            "status",
            "status_label",
            "distance_km",
            "estimated_drive_minutes",
            "fare",
            "route_geometry",
            "package_weight_kg",
            "requested_category_id",
            "requested_category_name",
            "requested_category_bidding",
            "payment_method",
            "latest_note",
            "decline_reason",
            "accepted_at",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
            "selected_driver_id",
            "customer_phone",
            "customer_latitude",
            "customer_longitude",
            "route",
            "timeline",
            "rated",
        ]
        read_only_fields = ["public_id", "status", "latest_note", "decline_reason"]

    def get_assigned_vehicle(self, obj):
        if not obj.assigned_vehicle_id:
            return None
        from vehicles.serializers import VehicleSerializer

        return VehicleSerializer(obj.assigned_vehicle).data

    def get_route(self, obj):
        return f"{obj.pickup_location} > {obj.delivery_location}"

    def get_rated(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return obj.ratings.filter(customer_id=user.id).exists()

    def create(self, validated_data):
        request = self.context["request"]
        selected_driver_id = validated_data.pop("selected_driver_id", None)
        customer_phone = (validated_data.pop("customer_phone", "") or "").strip()
        customer_latitude = validated_data.pop("customer_latitude", None)
        customer_longitude = validated_data.pop("customer_longitude", None)
        user = request.user
        request_source = validated_data.pop("request_source", None) or user.role
        if user.role == User.Role.DISPATCHER and not customer_phone:
            raise serializers.ValidationError(
                {
                    "customer_phone": "Customer phone number is required for dispatcher route requests."
                }
            )
        customer = (
            user
            if user.role == User.Role.CUSTOMER
            else validated_data.pop("customer", None)
        )
        if customer is None:
            customer = User.objects.filter(role=User.Role.CUSTOMER).first()

        pickup_location = validated_data.get("pickup_location", "")
        delivery_location = validated_data.get("delivery_location", "")

        distance_km = validated_data.pop("distance_km", None)
        estimated_drive_minutes = validated_data.pop("estimated_drive_minutes", None)
        validated_data.pop("fare", 0)
        route_geometry = validated_data.pop("route_geometry", None)

        if distance_km is None or estimated_drive_minutes is None:
            distance_km_calc, estimated_drive_minutes_calc = get_route_info(
                pickup_location, delivery_location
            )
            if distance_km is None:
                distance_km = (
                    distance_km_calc
                    if distance_km_calc != Decimal("0.00")
                    else Decimal("8.40")
                )
            if estimated_drive_minutes is None:
                estimated_drive_minutes = (
                    estimated_drive_minutes_calc
                    if estimated_drive_minutes_calc != 0
                    else 22
                )

        requested_category = validated_data.get("requested_category")
        fare_settings_obj = FareSettings.get_solo()
        base_fare = (
            requested_category.base_fare
            if requested_category
            else fare_settings_obj.base_fare
        )
        per_km_rate = (
            requested_category.per_km_rate
            if requested_category
            else fare_settings_obj.per_km_rate
        )
        per_minute_rate = (
            requested_category.per_minute_rate
            if requested_category
            else fare_settings_obj.per_minute_rate
        )
        payment_method = validated_data.get("payment_method") or "mixed"

        if payment_method == "distance":
            distance_charge = Decimal(distance_km) * per_km_rate
            time_charge = Decimal("0")
        elif payment_method == "time":
            distance_charge = Decimal("0")
            time_charge = Decimal(estimated_drive_minutes) * per_minute_rate
        else:
            distance_charge = Decimal(distance_km) * per_km_rate
            time_charge = (
                Decimal(estimated_drive_minutes) * per_minute_rate
                if estimated_drive_minutes >= 60
                else Decimal("0")
            )

        fare = base_fare + distance_charge + time_charge

        package_weight_kg = validated_data.pop("package_weight_kg", None)
        if package_weight_kg is None:
            package_weight_kg = Decimal("0")

        delivery = Delivery.objects.create(
            customer=customer,
            dispatcher=user if user.role == User.Role.DISPATCHER else None,
            customer_phone=customer_phone,
            request_source=request_source,
            distance_km=distance_km,
            package_weight_kg=package_weight_kg,
            estimated_drive_minutes=estimated_drive_minutes,
            fare=fare,
            route_geometry=route_geometry,
            requested_vehicle_type=validated_data.pop("requested_vehicle_type", "")
            or "",
            latest_note="Awaiting driver response.",
            **validated_data,
        )
        customer_coords = None
        if customer_latitude is not None and customer_longitude is not None:
            if (
                -90 <= float(customer_latitude) <= 90
                and -180 <= float(customer_longitude) <= 180
            ):
                customer_coords = (float(customer_latitude), float(customer_longitude))

        if requested_category and getattr(requested_category, "bidding", False):
            from deliveries.assignment import create_bid_request

            create_bid_request(
                delivery,
                radius_km=get_bidding_radius_km(requested_category),
                customer_coords=customer_coords,
            )
        else:
            from deliveries.assignment import assign_driver

            assign_driver(
                delivery,
                selected_driver_id=selected_driver_id,
                requested_by=user,
                customer_phone_override=customer_phone,
                customer_coords=customer_coords,
            )
        DeliveryEvent.objects.create(
            delivery=delivery,
            actor=user,
            event_type=DeliveryEvent.EventType.CREATED,
            message="Delivery request created.",
        )
        return delivery


class DeliveryActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["accept", "decline", "start", "complete", "confirm_reach", "reassign"]
    )
    reason = serializers.CharField(required=False, allow_blank=True)
    driver_id = serializers.IntegerField(required=False)
