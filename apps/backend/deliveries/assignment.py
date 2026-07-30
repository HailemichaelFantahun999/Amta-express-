import logging
import math
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from users.models import User
from features.auth.sms import format_phone_for_sms, send_sms
from deliveries.models import Delivery, DeliveryEvent
from features.notifications.models import Notification
from bidding.models import BidRequest
from features.notifications.notifications_service import create_notification


def parse_lat_lng(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1].strip()
    text = text.replace(" ", "")
    parts = text.split(",")
    if len(parts) != 2:
        return None
    try:
        lat = float(parts[0])
        lng = float(parts[1])
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def haversine_km(lat1, lng1, lat2, lng2):
    radius = 6371.0
    lat1_rad, lng1_rad = math.radians(lat1), math.radians(lng1)
    lat2_rad, lng2_rad = math.radians(lat2), math.radians(lng2)
    dlat = lat2_rad - lat1_rad
    dlng = lng2_rad - lng1_rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
    )
    return radius * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _filter_drivers_by_category(drivers, category=None):
    if category is None:
        return drivers
    return drivers.filter(
        assigned_vehicle__isnull=False,
        assigned_vehicle__category=category,
    )


def get_customer_nearby_drivers(
    delivery,
    excluded_driver_ids=None,
    radius_km=10.0,
    customer_coords=None,
    category=None,
):
    excluded_ids = set(excluded_driver_ids or [])
    reference_coords = customer_coords or parse_lat_lng(delivery.pickup_location)
    if not reference_coords:
        return []

    customer_lat, customer_lng = reference_coords
    candidates = User.objects.filter(
        role=User.Role.DRIVER,
        status=User.Status.AVAILABLE,
        last_location_lat__isnull=False,
        last_location_lng__isnull=False,
    )
    if excluded_ids:
        candidates = candidates.exclude(id__in=excluded_ids)
    candidates = _filter_drivers_by_category(candidates, category=category)

    ranked = []
    for driver in candidates:
        distance_km = haversine_km(
            customer_lat,
            customer_lng,
            float(driver.last_location_lat),
            float(driver.last_location_lng),
        )
        if distance_km >= radius_km:
            continue
        ranked.append({"driver": driver, "distance_km": distance_km})

    ranked.sort(
        key=lambda item: (
            item["distance_km"],
            -float(item["driver"].rating or 0),
            -(
                item["driver"].last_active_at.timestamp()
                if item["driver"].last_active_at
                else 0
            ),
        )
    )
    return ranked


def get_best_available_driver(delivery, category=None):
    available_drivers = User.objects.filter(
        role=User.Role.DRIVER,
        status=User.Status.AVAILABLE,
        last_location_lat__isnull=False,
        last_location_lng__isnull=False,
    )
    available_drivers = _filter_drivers_by_category(
        available_drivers, category=category
    )

    if not available_drivers.exists():
        return None

    pickup_coords = parse_lat_lng(delivery.pickup_location)
    if not pickup_coords:
        return get_best_available_driver_fallback(delivery)

    pickup_lat, pickup_lng = pickup_coords
    ranked_drivers = []

    for driver in available_drivers:
        distance_km = haversine_km(
            pickup_lat,
            pickup_lng,
            float(driver.last_location_lat),
            float(driver.last_location_lng),
        )

        if distance_km > 10.0:
            continue

        score = 0.0

        distance_score = max(0, 10 - distance_km)
        score += distance_score * 0.3

        rating = float(driver.rating or 0)
        score += min(rating, 5.0) * 0.25

        performance = float(driver.performance_score or 0)
        score += min(performance, 100) * 0.25

        recent_deliveries = Delivery.objects.filter(
            assigned_driver=driver,
            status__in=[Delivery.Status.DELIVERED],
            completed_at__gte=timezone.now() - timedelta(days=7),
        ).count()
        recent_score = min(recent_deliveries * 2, 10)
        score += recent_score * 0.15

        if driver.last_location_lat and driver.last_location_lng:
            score += 1.0 * 0.05

        ranked_drivers.append(
            {
                "driver": driver,
                "distance_km": distance_km,
                "score": score,
            }
        )

    ranked_drivers.sort(key=lambda item: (-item["score"], item["distance_km"]))

    return ranked_drivers[0]["driver"] if ranked_drivers else None


def get_best_available_driver_fallback(delivery, excluded_driver_ids=None):
    available_drivers = User.objects.filter(
        role=User.Role.DRIVER,
        status=User.Status.AVAILABLE,
    )

    if excluded_driver_ids:
        available_drivers = available_drivers.exclude(id__in=excluded_driver_ids)

    if not available_drivers.exists():
        return None

    best_driver = None
    best_score = -1

    for driver in available_drivers:
        score = 0

        score += float(driver.rating or 0) * 0.4

        score += float(driver.performance_score or 0) * 0.3

        recent_deliveries = Delivery.objects.filter(
            assigned_driver=driver,
            status__in=[Delivery.Status.DELIVERED],
            completed_at__gte=timezone.now() - timedelta(days=7),
        ).count()
        score += min(recent_deliveries * 2, 10)

        if driver.last_location_lat and driver.last_location_lng:
            score += 5

        if score > best_score:
            best_score = score
            best_driver = driver

    return best_driver


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
        logger = logging.getLogger(__name__)
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


def assign_driver(
    delivery,
    selected_driver_id=None,
    requested_by=None,
    customer_phone_override="",
    excluded_driver_ids=None,
    customer_coords=None,
):
    requested_category = delivery.requested_category

    if selected_driver_id:
        driver = User.objects.filter(
            pk=selected_driver_id, role=User.Role.DRIVER
        ).first()
    else:
        if delivery.request_source == Delivery.RequestSource.CUSTOMER:
            ranked_nearby = get_customer_nearby_drivers(
                delivery,
                excluded_driver_ids=excluded_driver_ids,
                radius_km=10.0,
                customer_coords=customer_coords,
                category=requested_category,
            )
            driver = ranked_nearby[0]["driver"] if ranked_nearby else None
        else:
            driver = get_best_available_driver(delivery, category=requested_category)

    if not driver:
        delivery.status = Delivery.Status.PENDING_ASSIGNMENT
        delivery.latest_note = "No available drivers"
        delivery.save(update_fields=["status", "latest_note", "updated_at"])
        return delivery

    delivery.assigned_driver = driver
    delivery.assigned_vehicle = None
    delivery.status = Delivery.Status.PENDING_DRIVER_RESPONSE
    delivery.latest_note = (
        f"Assigned to {driver.get_full_name().strip() or driver.email}. "
        "Waiting for response (5-30 seconds)."
    )
    delivery.decline_reason = ""

    if not delivery.pk:
        delivery.save()
    else:
        delivery.save(
            update_fields=[
                "assigned_driver",
                "assigned_vehicle",
                "status",
                "latest_note",
                "decline_reason",
                "updated_at",
            ]
        )

    DeliveryEvent.objects.create(
        delivery=delivery,
        actor=requested_by,
        event_type=DeliveryEvent.EventType.ASSIGNED,
        message=(
            f"Driver {(driver.get_full_name().strip() or driver.email)} "
            "assigned to delivery."
        ),
    )
    create_notification(
        driver,
        "New delivery assignment",
        f"You have been assigned to {delivery.public_id}.",
        delivery,
    )
    create_notification(
        delivery.assigned_driver,
        "New Assignment",
        f"{delivery.public_id} has been assigned to you.",
        delivery,
    )
    return delivery


def check_and_reassign_timeout_deliveries():
    timeout_threshold = timezone.now() - timedelta(seconds=30)

    timeout_deliveries = Delivery.objects.filter(
        status=Delivery.Status.PENDING_DRIVER_RESPONSE,
        updated_at__lte=timeout_threshold,
    )

    for delivery in timeout_deliveries:
        reassign_delivery(delivery, "timeout")


def reassign_delivery(delivery, reason="timeout"):
    excluded_driver_ids = []
    previous_driver = delivery.assigned_driver

    if previous_driver:
        excluded_driver_ids.append(previous_driver.id)

        DeliveryEvent.objects.create(
            delivery=delivery,
            actor=previous_driver,
            event_type=DeliveryEvent.EventType.DECLINED,
            message=(
                f"Driver {previous_driver.get_full_name().strip() or previous_driver.email} "
                f'{"timed out" if reason == "timeout" else "declined"} assignment.'
            ),
        )

        create_notification(
            previous_driver,
            "Delivery Reassigned",
            f"Delivery {delivery.public_id} has been reassigned to another driver.",
            delivery,
        )

    if delivery.request_source == Delivery.RequestSource.CUSTOMER:
        ranked_nearby = get_customer_nearby_drivers(
            delivery,
            excluded_driver_ids=excluded_driver_ids,
            radius_km=10.0,
        )
        next_driver = ranked_nearby[0]["driver"] if ranked_nearby else None
    else:
        next_driver = get_best_available_driver_fallback(delivery, excluded_driver_ids)

    if not next_driver:
        delivery.status = Delivery.Status.PENDING_ASSIGNMENT
        delivery.latest_note = (
            f"No available drivers after "
            f'{"timeout" if reason == "timeout" else "decline"}'
        )
        delivery.assigned_driver = None
        delivery.save(
            update_fields=["status", "latest_note", "assigned_driver", "updated_at"]
        )
        return delivery

    delivery.assigned_driver = next_driver
    delivery.assigned_vehicle = None
    delivery.status = Delivery.Status.PENDING_DRIVER_RESPONSE
    delivery.latest_note = (
        f"Reassigned to {next_driver.get_full_name().strip() or next_driver.email}. "
        "Waiting for response (5-30 seconds)."
    )
    delivery.decline_reason = ""
    delivery.save(
        update_fields=[
            "assigned_driver",
            "assigned_vehicle",
            "status",
            "latest_note",
            "decline_reason",
            "updated_at",
        ]
    )

    DeliveryEvent.objects.create(
        delivery=delivery,
        event_type=DeliveryEvent.EventType.ASSIGNED,
        message=(
            f"Driver {(next_driver.get_full_name().strip() or next_driver.email)} "
            "assigned to delivery."
        ),
    )

    create_notification(
        next_driver,
        "New delivery assignment",
        f"{delivery.public_id} has been assigned to you.",
        delivery,
    )

    if reason in ["timeout", "decline"]:
        create_notification(
            next_driver,
            "Delivery Reassignment",
            f"{delivery.public_id} was reassigned from previous driver.",
            delivery,
        )

    responsible_party = None
    notification_title = "Driver Assigned to Your Delivery"
    notification_message = (
        f"Driver {next_driver.get_full_name().strip() or next_driver.email} "
        f"has been assigned to your delivery {delivery.public_id}."
    )

    if delivery.customer:
        responsible_party = delivery.customer
    elif delivery.dispatcher:
        responsible_party = delivery.dispatcher
    else:
        responsible_party = None
        notification_title = "Driver Assigned to Delivery"
        notification_message = (
            f"You have been assigned to delivery {delivery.public_id}."
        )

    if responsible_party:
        create_notification(
            responsible_party,
            notification_title,
            notification_message,
            delivery,
        )

    return delivery


def pickup_coords_for_delivery(delivery):
    return parse_lat_lng(delivery.pickup_location)


def driver_matches_bid_category(driver, category):
    if not category:
        return False
    vehicle = getattr(driver, "assigned_vehicle", None)
    if not vehicle:
        return False
    if vehicle.category_id is None:
        return True
    return vehicle.category_id == category.id


def driver_distance_to_pickup_km(driver, delivery):
    pickup = pickup_coords_for_delivery(delivery)
    if (
        not pickup
        or driver.last_location_lat is None
        or driver.last_location_lng is None
    ):
        return None
    try:
        return haversine_km(
            pickup[0],
            pickup[1],
            float(driver.last_location_lat),
            float(driver.last_location_lng),
        )
    except (TypeError, ValueError):
        return None


def is_driver_eligible_for_bid(driver, bid_request):
    if bid_request.status != BidRequest.Status.OPEN:
        return False
    if driver.role != User.Role.DRIVER:
        return False
    if driver.status not in (User.Status.AVAILABLE, User.Status.ACTIVE):
        return False
    if not driver_matches_bid_category(driver, bid_request.category):
        return False

    pickup = pickup_coords_for_delivery(bid_request.delivery)
    if not pickup:
        return False

    distance_km = driver_distance_to_pickup_km(driver, bid_request.delivery)
    if distance_km is None:
        return False
    return distance_km <= float(bid_request.radius_km)


def _iter_bid_driver_candidates(category):
    return (
        User.objects.filter(
            role=User.Role.DRIVER,
            status__in=[User.Status.AVAILABLE, User.Status.ACTIVE],
            assigned_vehicle__isnull=False,
        )
        .filter(
            Q(assigned_vehicle__category=category)
            | Q(assigned_vehicle__category__isnull=True),
        )
        .select_related("assigned_vehicle", "assigned_vehicle__category")
    )


def sync_eligible_drivers_for_bid_request(bid_request, notify_new=True):
    delivery = bid_request.delivery
    category = bid_request.category
    pickup = pickup_coords_for_delivery(delivery)
    if not pickup:
        return 0, {"invalid_pickup": True}

    previously_eligible = set(bid_request.eligible_drivers.values_list("id", flat=True))
    eligible = []
    skipped = {"no_location": 0, "wrong_category": 0, "too_far": 0}

    for driver in _iter_bid_driver_candidates(category):
        if not driver_matches_bid_category(driver, category):
            skipped["wrong_category"] += 1
            continue

        distance_km = driver_distance_to_pickup_km(driver, delivery)
        if distance_km is None:
            skipped["no_location"] += 1
            continue
        if distance_km > float(bid_request.radius_km):
            skipped["too_far"] += 1
            continue

        eligible.append(driver)
        if notify_new and driver.id not in previously_eligible:
            create_notification(
                driver,
                "New bidding request",
                (
                    f"Bidding request {delivery.public_id} ({category.name}) ~{distance_km:.1f} km "
                    f"from origin — {delivery.pickup_location} → {delivery.delivery_location}."
                ),
                delivery,
                notification_type=Notification.Type.BIDDING_OPEN,
                bid_request=bid_request,
                link_path="/driver/bidding",
            )

    bid_request.eligible_drivers.set(eligible)
    return len(eligible), skipped


def refresh_driver_bid_eligibility(driver):
    if driver.role != User.Role.DRIVER:
        return 0
    attached = 0
    for bid_request in BidRequest.objects.filter(
        status=BidRequest.Status.OPEN
    ).select_related("delivery", "category"):
        if is_driver_eligible_for_bid(driver, bid_request):
            bid_request.eligible_drivers.add(driver)
            attached += 1
    return attached


def create_bid_request(delivery, radius_km=None, customer_coords=None):
    if not delivery.requested_category:
        return 0

    if not pickup_coords_for_delivery(delivery):
        delivery.latest_note = (
            "Bidding failed: origin coordinates are invalid (use lat,lng pickup)."
        )
        delivery.save(update_fields=["latest_note", "updated_at"])
        return 0

    if radius_km is None:
        from fares.fare_utils import get_bidding_radius_km

        radius_km = get_bidding_radius_km(delivery.requested_category)

    bid_request = BidRequest.objects.create(
        delivery=delivery,
        customer=delivery.customer,
        category=delivery.requested_category,
        radius_km=radius_km,
        status=BidRequest.Status.OPEN,
    )

    eligible_count, skipped = sync_eligible_drivers_for_bid_request(
        bid_request, notify_new=True
    )
    category = delivery.requested_category

    delivery.status = Delivery.Status.PENDING_ASSIGNMENT
    delivery.assigned_driver = None
    delivery.assigned_vehicle = None

    if eligible_count:
        delivery.latest_note = (
            f"Bidding open: {eligible_count} driver(s) within {radius_km} km of origin notified. "
            f"Route {delivery.distance_km} km, {delivery.package_weight_kg} kg."
        )
    else:
        delivery.latest_note = (
            f"Bidding open: 0 drivers within {radius_km} km of origin ({delivery.pickup_location}). "
            f'Need category "{category.name}", status available, vehicle assigned, and live GPS. '
            f'Skipped: {skipped.get("too_far", 0)} too far, {skipped.get("no_location", 0)} no GPS, '
            f'{skipped.get("wrong_category", 0)} wrong category.'
        )

    delivery.save(
        update_fields=[
            "status",
            "latest_note",
            "assigned_driver",
            "assigned_vehicle",
            "updated_at",
        ],
    )

    from bidding.bidding_notify import notify_bidding_open

    notify_bidding_open(bid_request)

    return eligible_count
