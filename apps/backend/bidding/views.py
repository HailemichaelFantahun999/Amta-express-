import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import User
from features.notifications.models import Notification
from bidding.models import (
    Bid,
    BidNegotiation,
    BidRequest,
)
from bidding.bidding import award_bid, cancel_bid_request
from bidding.negotiation import (
    customer_counter_bid,
    driver_accept_counter,
    driver_decline_counter,
    record_negotiation,
)
from bidding.bidding_notify import (
    notify_bid_received,
    notify_counter_accepted,
    notify_counter_declined,
    notify_counter_offer,
)
from bidding.serializers import (
    BidCounterSerializer,
    BidCreateSerializer,
    BidRequestSerializer,
    BidSerializer,
)
from fares.fare_utils import calculate_bid_amount
from features.notifications.serializers import NotificationSerializer

logger = logging.getLogger(__name__)


class BidRequestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BidRequestSerializer
    permission_classes = [IsAuthenticated]
    queryset = (
        BidRequest.objects.select_related(
            "delivery",
            "customer",
            "category",
            "winning_bid",
            "winning_bid__driver",
        )
        .prefetch_related(
            "bids",
            "bids__driver",
            "bids__negotiations",
            "bids__negotiations__actor",
            "eligible_drivers",
        )
        .order_by("-created_at")
    )

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.role == User.Role.CUSTOMER:
            return qs.filter(customer=user)
        if user.role == User.Role.DRIVER:
            from features.deliveries.assignment import (
                is_driver_eligible_for_bid,
                refresh_driver_bid_eligibility,
            )

            refresh_driver_bid_eligibility(user)
            open_requests = qs.filter(status=BidRequest.Status.OPEN)
            matching_ids = [
                br.id
                for br in open_requests.select_related("delivery", "category")
                if br.category and is_driver_eligible_for_bid(user, br)
            ]
            if not matching_ids:
                return qs.none()
            return qs.filter(id__in=matching_ids)
        return qs

    @action(detail=True, methods=["post"], url_path="refresh-drivers")
    def refresh_drivers(self, request, pk=None):
        bid_request = self.get_object()
        user = request.user
        if user.role not in (User.Role.CUSTOMER, User.Role.ADMIN) or (
            user.role == User.Role.CUSTOMER and bid_request.customer_id != user.id
        ):
            return Response(
                {"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN
            )
        if bid_request.status != BidRequest.Status.OPEN:
            return Response(
                {"detail": "This bidding request is no longer open."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from deliveries.assignment import sync_eligible_drivers_for_bid_request

        count, skipped = sync_eligible_drivers_for_bid_request(
            bid_request, notify_new=True
        )
        delivery = bid_request.delivery
        delivery.latest_note = (
            f"Bidding refreshed: {count} driver(s) within {bid_request.radius_km} km of origin. "
            f'Skipped {skipped.get("too_far", 0)} too far, {skipped.get("no_location", 0)} no GPS.'
        )
        delivery.save(update_fields=["latest_note", "updated_at"])
        bid_request.refresh_from_db()
        return Response(
            BidRequestSerializer(bid_request, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="award")
    def award(self, request, pk=None):
        bid_request = self.get_object()
        user = request.user
        if user.role not in (User.Role.CUSTOMER, User.Role.ADMIN) or (
            user.role == User.Role.CUSTOMER and bid_request.customer_id != user.id
        ):
            return Response(
                {
                    "detail": "Only the customer who created this request can award a bid."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        bid_id = request.data.get("bid_id")
        if not bid_id:
            return Response(
                {"detail": "bid_id is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        bid = (
            bid_request.bids.filter(pk=bid_id, status=Bid.Status.PENDING)
            .select_related("driver")
            .first()
        )
        if not bid:
            return Response(
                {"detail": "Bid not found or no longer available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            award_bid(bid_request, bid, awarded_by=user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        bid_request.refresh_from_db()
        return Response(
            BidRequestSerializer(bid_request, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        bid_request = self.get_object()
        user = request.user
        if user.role not in (User.Role.CUSTOMER, User.Role.ADMIN) or (
            user.role == User.Role.CUSTOMER and bid_request.customer_id != user.id
        ):
            return Response(
                {
                    "detail": "Only the customer who created this request can cancel bidding."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            cancel_bid_request(bid_request, cancelled_by=user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        bid_request.refresh_from_db()
        return Response(
            BidRequestSerializer(bid_request, context={"request": request}).data
        )


class BidViewSet(viewsets.ModelViewSet):
    serializer_class = BidSerializer
    permission_classes = [IsAuthenticated]
    queryset = (
        Bid.objects.select_related(
            "bid_request", "bid_request__category", "bid_request__delivery", "driver"
        )
        .prefetch_related("negotiations", "negotiations__actor")
        .order_by("amount", "created_at")
    )
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.role == User.Role.DRIVER:
            return qs.filter(driver=user)
        if user.role == User.Role.CUSTOMER:
            return qs.filter(bid_request__customer=user)
        return qs

    def create(self, request, *args, **kwargs):
        user = request.user
        if user.role != User.Role.DRIVER:
            return Response(
                {"detail": "Only drivers may place bids."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = BidCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bid_request = serializer.validated_data["bid_request"]

        from deliveries.assignment import (
            is_driver_eligible_for_bid,
            refresh_driver_bid_eligibility,
        )

        refresh_driver_bid_eligibility(user)
        if not is_driver_eligible_for_bid(user, bid_request):
            return Response(
                {
                    "detail": "You are not eligible for this bidding request (wrong category or outside radius)."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(user, "assigned_vehicle", None):
            return Response(
                {"detail": "You must be assigned to a vehicle to bid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        category = bid_request.category
        distance_km = bid_request.delivery.distance_km
        weight_kg = bid_request.delivery.package_weight_kg
        bid_method = serializer.validated_data["bid_method"]
        unit_price = serializer.validated_data["unit_price"]

        if bid_method == "km" and unit_price < category.per_km_rate:
            return Response(
                {
                    "detail": f"Per km price cannot be lower than category minimum {category.per_km_rate}."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if bid_method == "kg" and unit_price < category.per_kg_rate:
            return Response(
                {
                    "detail": f"Per kg price cannot be lower than category minimum {category.per_kg_rate}."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = calculate_bid_amount(
            category, bid_method, unit_price, distance_km, weight_kg
        )
        message = serializer.validated_data.get("message", "")

        had_pending_counter = False
        existing = Bid.objects.filter(bid_request=bid_request, driver=user).first()
        if existing and existing.counter_status == "pending":
            had_pending_counter = True
            driver_decline_counter(existing, user)

        bid, created = Bid.objects.update_or_create(
            bid_request=bid_request,
            driver=user,
            defaults={
                "bid_method": bid_method,
                "unit_price": unit_price,
                "distance_km": distance_km,
                "weight_kg": weight_kg,
                "amount": amount,
                "message": message,
                "status": Bid.Status.PENDING,
            },
        )

        record_negotiation(
            bid,
            user,
            BidNegotiation.Party.DRIVER,
            bid_method,
            unit_price,
            amount,
            message or ("Initial bid" if created else "Updated bid"),
        )

        if had_pending_counter:
            notify_counter_declined(bid)
        else:
            notify_bid_received(bid, created=created)

        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(BidSerializer(bid).data, status=status_code)

    @action(detail=True, methods=["post"], url_path="counter")
    def counter(self, request, pk=None):
        bid = self.get_object()
        user = request.user
        if user.role != User.Role.CUSTOMER or bid.bid_request.customer_id != user.id:
            return Response(
                {"detail": "Only the customer may counter this bid."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = BidCounterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            bid = customer_counter_bid(
                bid,
                user,
                serializer.validated_data["unit_price"],
                serializer.validated_data.get("message", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        notify_counter_offer(bid)
        return Response(BidSerializer(bid).data)

    @action(detail=True, methods=["post"], url_path="accept-counter")
    def accept_counter(self, request, pk=None):
        bid = self.get_object()
        user = request.user
        if user.role != User.Role.DRIVER or bid.driver_id != user.id:
            return Response(
                {"detail": "Only the bidding driver may accept this counter."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            bid = driver_accept_counter(bid, user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        notify_counter_accepted(bid)
        return Response(BidSerializer(bid).data)

    @action(detail=True, methods=["post"], url_path="decline-counter")
    def decline_counter(self, request, pk=None):
        bid = self.get_object()
        user = request.user
        if user.role != User.Role.DRIVER or bid.driver_id != user.id:
            return Response(
                {"detail": "Only the bidding driver may decline this counter."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            bid = driver_decline_counter(bid, user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        from bidding.bidding_notify import notify_counter_rejected

        notify_counter_rejected(bid)
        return Response(BidSerializer(bid).data)


BIDDING_NOTIFICATION_TYPES = [
    Notification.Type.BIDDING_OPEN,
    Notification.Type.BID_RECEIVED,
    Notification.Type.BID_UPDATED,
    Notification.Type.BID_COUNTER,
    Notification.Type.COUNTER_ACCEPTED,
    Notification.Type.COUNTER_DECLINED,
    Notification.Type.BID_AWARDED,
    Notification.Type.BID_LOST,
]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bidding_summary(request):
    user = request.user
    unread = Notification.objects.filter(
        recipient=user,
        is_read=False,
        notification_type__in=BIDDING_NOTIFICATION_TYPES,
    ).count()
    recent = Notification.objects.filter(
        recipient=user,
        notification_type__in=BIDDING_NOTIFICATION_TYPES,
    ).order_by("-created_at")[:10]
    recent_data = NotificationSerializer(recent, many=True).data

    if user.role == User.Role.CUSTOMER:
        open_requests = BidRequest.objects.filter(
            customer=user, status=BidRequest.Status.OPEN
        ).count()
        pending_bids = Bid.objects.filter(
            bid_request__customer=user,
            bid_request__status=BidRequest.Status.OPEN,
            status=Bid.Status.PENDING,
        ).count()
        pending_counters = Bid.objects.filter(
            bid_request__customer=user,
            bid_request__status=BidRequest.Status.OPEN,
            status=Bid.Status.PENDING,
            counter_status="pending",
        ).count()
        return Response(
            {
                "role": user.role,
                "open_requests": open_requests,
                "pending_bids": pending_bids,
                "pending_counters": pending_counters,
                "unread_notifications": unread,
                "recent_notifications": recent_data,
                "bidding_path": "/customer/bidding",
            }
        )

    if user.role == User.Role.DRIVER:
        from features.deliveries.assignment import (
            is_driver_eligible_for_bid,
            refresh_driver_bid_eligibility,
        )

        refresh_driver_bid_eligibility(user)
        open_requests = 0
        for br in BidRequest.objects.filter(
            status=BidRequest.Status.OPEN
        ).select_related("delivery", "category"):
            if is_driver_eligible_for_bid(user, br):
                open_requests += 1
        pending_counters = Bid.objects.filter(
            driver=user,
            counter_status="pending",
            bid_request__status=BidRequest.Status.OPEN,
        ).count()
        my_bids = Bid.objects.filter(
            driver=user,
            bid_request__status=BidRequest.Status.OPEN,
            status=Bid.Status.PENDING,
        ).count()
        return Response(
            {
                "role": user.role,
                "open_requests": open_requests,
                "pending_bids": my_bids,
                "pending_counters": pending_counters,
                "unread_notifications": unread,
                "recent_notifications": recent_data,
                "bidding_path": "/driver/bidding",
            }
        )

    return Response(
        {
            "role": user.role,
            "open_requests": 0,
            "pending_bids": 0,
            "pending_counters": 0,
            "unread_notifications": unread,
            "recent_notifications": recent_data,
            "bidding_path": "",
        }
    )
