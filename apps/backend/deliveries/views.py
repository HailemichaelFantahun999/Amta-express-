import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import User
from features.auth.sms import format_phone_for_sms, send_sms
from deliveries.assignment import assign_driver
from features.notifications.notifications_service import create_notification
from deliveries.models import Delivery, DeliveryEvent
from deliveries.serializers import (
    DeliveryActionSerializer,
    DeliverySerializer,
)
from fares.fare_utils import get_bidding_radius_km

logger = logging.getLogger(__name__)


def send_assignment_sms_to_customer(delivery, driver, customer_phone_override=""):
    customer_phone = (customer_phone_override or "").strip()
    if not customer_phone:
        customer_phone = (delivery.customer_phone or "").strip()
    if not customer_phone:
        customer_phone = (
            User.objects.filter(pk=delivery.customer_id)
            .values_list("phone", flat=True)
            .first()
            or ""
        ).strip()
    if not customer_phone:
        create_notification(
            delivery.customer,
            "Phone number required",
            f"Add your phone number in profile to receive driver assignment SMS for {delivery.public_id}.",
            delivery,
        )
        if delivery.dispatcher:
            create_notification(
                delivery.dispatcher,
                "Customer phone missing",
                f"Customer phone is missing for {delivery.public_id}; SMS was not sent.",
                delivery,
            )
        logger.info(
            "Customer phone missing for delivery %s. Assignment SMS skipped.",
            delivery.public_id,
        )
        return

    customer_phone = format_phone_for_sms(customer_phone)

    driver_name = driver.get_full_name().strip() or driver.email
    driver_phone = (driver.phone or "").strip() or "N/A"
    driver_license = (driver.license_number or "").strip() or "N/A"
    driver_vehicle = "N/A"
    driver_rating = f'{driver.rating or "N/A"}'

    if delivery.distance_km and delivery.distance_km > 50:
        message = (
            f"🚚 LONG DISTANCE DELIVERY {delivery.public_id}\n"
            f"Driver: {driver_name} (⭐{driver_rating})\n"
            f"Vehicle: {driver_vehicle} | License: {driver_license}\n"
            f"Phone: {driver_phone}\n"
            f"Distance: {delivery.distance_km:.1f}km | Est: {delivery.estimated_drive_minutes}min"
        )
    elif delivery.package_details and any(
        word in delivery.package_details.lower()
        for word in ["fragile", "urgent", "express"]
    ):
        message = (
            f"📦 SPECIAL DELIVERY {delivery.public_id}\n"
            f"Driver: {driver_name} (⭐{driver_rating})\n"
            f"Vehicle: {driver_vehicle} | License: {driver_license}\n"
            f"Phone: {driver_phone}\n"
            f"Note: Special handling required for your package"
        )
    else:
        message = (
            f"📬 DELIVERY {delivery.public_id}\n"
            f"Driver: {driver_name} (⭐{driver_rating})\n"
            f"Vehicle: {driver_vehicle} | License: {driver_license}\n"
            f"Phone: {driver_phone}\n"
            f'Est. arrival: {delivery.delivery_window or "ASAP"}'
        )

    sent, details = send_sms(customer_phone, message)
    if not sent:
        title = (
            "Assignment SMS not configured"
            if "not configured" in details.lower()
            else "Assignment SMS failed"
        )
        create_notification(
            delivery.customer,
            title,
            f'SMS for {delivery.public_id} failed: {details or "Unknown error."}',
            delivery,
        )
        if delivery.dispatcher:
            create_notification(
                delivery.dispatcher,
                title,
                f'SMS for {delivery.public_id} failed: {details or "Unknown error."}',
                delivery,
            )


class DeliveryViewSet(viewsets.ModelViewSet):
    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]
    queryset = (
        Delivery.objects.select_related(
            "customer", "dispatcher", "assigned_driver", "assigned_vehicle"
        )
        .prefetch_related("events")
        .order_by("-created_at")
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.role == User.Role.CUSTOMER:
            queryset = queryset.filter(customer=user)
        elif user.role == User.Role.DRIVER:
            queryset = queryset.filter(assigned_driver=user)
        status_value = self.request.query_params.get("status")
        search = self.request.query_params.get("search")
        if status_value:
            queryset = queryset.filter(status=status_value)
        if search:
            queryset = queryset.filter(
                Q(public_id__icontains=search)
                | Q(pickup_location__icontains=search)
                | Q(delivery_location__icontains=search)
                | Q(package_details__icontains=search)
            )
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        delivery = serializer.save()
        if delivery.assigned_driver:
            driver_name = (
                delivery.assigned_driver.get_full_name().strip()
                or delivery.assigned_driver.email
            )
            if request.user.role == User.Role.CUSTOMER and not request.data.get(
                "selected_driver_id"
            ):
                message = (
                    f"{delivery.public_id} was submitted successfully. "
                    f"Assigned driver: {driver_name}. "
                    "The request was also sent to the driver for response."
                )
            else:
                message = f"{delivery.public_id} was assigned to {driver_name} and is waiting for driver response."
        else:
            if request.user.role == User.Role.CUSTOMER:
                requested_category = delivery.requested_category
                if requested_category and getattr(requested_category, "bidding", False):
                    radius = get_bidding_radius_km(requested_category)
                else:
                    radius = 10.0
                message = f"No nearby online drivers available within {radius} km."
            else:
                message = "No available drivers"
        headers = self.get_success_headers(serializer.data)
        return Response(
            {**DeliverySerializer(delivery).data, "detail": message},
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class DeliveryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        delivery = (
            Delivery.objects.select_related(
                "customer", "dispatcher", "assigned_driver", "assigned_vehicle"
            )
            .prefetch_related("events")
            .get(pk=pk)
        )
        return Response(DeliverySerializer(delivery).data)


class DeliveryActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        delivery = Delivery.objects.select_related(
            "customer", "dispatcher", "assigned_driver", "assigned_vehicle"
        ).get(pk=pk)
        serializer = DeliveryActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        user = request.user

        if action == "accept":
            if delivery.assigned_driver != user:
                return Response(
                    {"detail": "Only the assigned driver can accept this delivery."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            delivery.status = Delivery.Status.ACCEPTED
            delivery.accepted_at = timezone.now()
            delivery.latest_note = "Driver accepted the delivery."
            user.status = User.Status.ON_TRIP
            user.save(update_fields=["status"])
            delivery.save(
                update_fields=["status", "accepted_at", "latest_note", "updated_at"]
            )
            DeliveryEvent.objects.create(
                delivery=delivery,
                actor=user,
                event_type=DeliveryEvent.EventType.ACCEPTED,
                message="Driver accepted the assignment.",
            )
            create_notification(
                delivery.customer,
                "Driver accepted",
                f"{delivery.public_id} was accepted by the driver.",
                delivery,
            )
            create_notification(
                delivery.dispatcher,
                "Driver accepted",
                f"{delivery.public_id} was accepted by the driver.",
                delivery,
            )

            send_assignment_sms_to_customer(
                delivery, user, customer_phone_override=delivery.customer_phone
            )
        elif action == "decline":
            if delivery.assigned_driver != user:
                return Response(
                    {"detail": "Only the assigned driver can decline this delivery."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            reason = (
                serializer.validated_data.get("reason")
                or "Driver declined the assignment."
            )
            declined_driver_name = user.get_full_name().strip() or user.email
            delivery.status = Delivery.Status.DECLINED
            delivery.decline_reason = reason
            delivery.latest_note = reason
            delivery.assigned_driver = None
            delivery.assigned_vehicle = None
            delivery.save(
                update_fields=[
                    "status",
                    "decline_reason",
                    "latest_note",
                    "assigned_driver",
                    "assigned_vehicle",
                    "updated_at",
                ]
            )
            DeliveryEvent.objects.create(
                delivery=delivery,
                actor=user,
                event_type=DeliveryEvent.EventType.DECLINED,
                message=reason,
            )
            if delivery.request_source == Delivery.RequestSource.CUSTOMER:
                previous_declines = list(
                    DeliveryEvent.objects.filter(
                        delivery=delivery,
                        event_type=DeliveryEvent.EventType.DECLINED,
                        actor__role=User.Role.DRIVER,
                    ).values_list("actor_id", flat=True)
                )
                excluded_ids = [
                    driver_id for driver_id in previous_declines if driver_id
                ]
                reassign_result = assign_driver(
                    delivery,
                    requested_by=delivery.customer,
                    customer_phone_override=delivery.customer_phone,
                    excluded_driver_ids=excluded_ids,
                )
                if reassign_result.assigned_driver:
                    next_driver_name = (
                        reassign_result.assigned_driver.get_full_name().strip()
                        or reassign_result.assigned_driver.email
                    )
                    create_notification(
                        delivery.customer,
                        "Driver declined",
                        (
                            f"{delivery.public_id} was declined by {declined_driver_name}. "
                            f"Request sent to next nearby driver: {next_driver_name}."
                        ),
                        delivery,
                    )
                else:
                    create_notification(
                        delivery.customer,
                        "Driver declined",
                        (
                            f"{delivery.public_id} was declined by {declined_driver_name}. "
                            "No other nearby online drivers are available."
                        ),
                        delivery,
                    )
            else:
                create_notification(
                    delivery.customer,
                    "Driver declined",
                    (
                        f"{delivery.public_id} was declined by {declined_driver_name}. "
                        "Please choose another driver."
                    ),
                    delivery,
                )
                create_notification(
                    delivery.dispatcher,
                    "Driver declined",
                    (
                        f"{delivery.public_id} was declined by {declined_driver_name}. "
                        "Please assign another driver."
                    ),
                    delivery,
                )
        elif action == "reassign":
            if user.role not in [
                User.Role.CUSTOMER,
                User.Role.DISPATCHER,
                User.Role.ADMIN,
            ]:
                return Response(
                    {
                        "detail": "Only customers, dispatchers, or admins can reassign drivers."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            assign_driver(
                delivery, serializer.validated_data.get("driver_id"), requested_by=user
            )
        elif action == "confirm_reach":
            delivery.latest_note = "Driver confirmed arrival at pickup."
            delivery.save(update_fields=["latest_note", "updated_at"])
            DeliveryEvent.objects.create(
                delivery=delivery,
                actor=user,
                event_type=DeliveryEvent.EventType.REACHED_PICKUP,
                message="Driver confirmed arrival at pickup.",
            )
        elif action == "start":
            delivery.status = Delivery.Status.IN_TRANSIT
            delivery.started_at = timezone.now()
            delivery.latest_note = "Delivery is now in transit."
            delivery.save(
                update_fields=["status", "started_at", "latest_note", "updated_at"]
            )
            DeliveryEvent.objects.create(
                delivery=delivery,
                actor=user,
                event_type=DeliveryEvent.EventType.STARTED,
                message="Delivery started.",
            )
        elif action == "complete":
            delivery.status = Delivery.Status.DELIVERED
            delivery.completed_at = timezone.now()
            delivery.latest_note = "Delivery completed successfully."
            if delivery.assigned_driver:
                delivery.assigned_driver.status = User.Status.AVAILABLE
                delivery.assigned_driver.save(update_fields=["status"])
            delivery.save(
                update_fields=["status", "completed_at", "latest_note", "updated_at"]
            )
            DeliveryEvent.objects.create(
                delivery=delivery,
                actor=user,
                event_type=DeliveryEvent.EventType.DELIVERED,
                message="Delivery completed.",
            )
            create_notification(
                delivery.customer,
                "Delivery completed",
                f"{delivery.public_id} has been delivered.",
                delivery,
            )
            create_notification(
                delivery.dispatcher,
                "Delivery completed",
                f"{delivery.public_id} has been delivered.",
                delivery,
            )
        return Response(DeliverySerializer(delivery).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def gebeta_directions_proxy(request):
    if not getattr(settings, "GEBETA_API_KEY", ""):
        return Response(
            {"detail": "Server missing GEBETA_API_KEY."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    def normalize_point(value: str) -> str:
        value = (value or "").strip()
        if value.startswith("{") and value.endswith("}"):
            value = value[1:-1].strip()
        value = value.replace(" ", "")
        return f"{{{value}}}" if value else ""

    origin = normalize_point(request.query_params.get("origin"))
    destination = normalize_point(request.query_params.get("destination"))
    waypoints_raw = (request.query_params.get("waypoints") or "").strip()
    instruction = (request.query_params.get("instruction") or "").strip()

    if not origin or not destination:
        return Response(
            {"detail": 'origin and destination are required (format: "{lat,lon}").'},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    params = {
        "origin": origin,
        "destination": destination,
        "apiKey": settings.GEBETA_API_KEY,
    }
    if waypoints_raw:
        points = [normalize_point(p) for p in waypoints_raw.split(";") if p.strip()]
        points = [p for p in points if p]
        if points:
            params["waypoints"] = ";".join(points)
    if instruction:
        params["instruction"] = instruction

    url = f"https://mapapi.gebeta.app/api/route/direction/?{urlencode(params, safe='{},')}"

    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            try:
                payload = json.loads(body)
            except Exception:
                payload = body
            return Response(payload, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"detail": f"Failed to fetch directions: {str(e)}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def gebeta_reverse_geocoding_proxy(request):
    if not getattr(settings, "GEBETA_API_KEY", ""):
        return Response(
            {"detail": "Server missing GEBETA_API_KEY."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    lat = (request.query_params.get("lat") or "").strip()
    lon = (request.query_params.get("lon") or "").strip()

    if not lat or not lon:
        return Response(
            {"detail": "lat and lon are required."},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    params = {"lat": lat, "lon": lon, "apiKey": settings.GEBETA_API_KEY}
    url = f"https://mapapi.gebeta.app/api/v1/route/revgeocoding?{urlencode(params)}"

    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            try:
                payload = json.loads(body)
            except Exception:
                payload = body
            return Response(payload, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"detail": f"Failed to fetch reverse geocoding results: {str(e)}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
