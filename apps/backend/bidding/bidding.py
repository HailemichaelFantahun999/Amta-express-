from deliveries.models import Delivery, DeliveryEvent
from bidding.models import Bid, BidRequest
from features.notifications.models import Notification
from features.notifications.notifications_service import create_notification


def award_bid(bid_request, bid, awarded_by):
    if bid_request.status != BidRequest.Status.OPEN:
        raise ValueError("This bidding request is no longer open.")
    if bid.bid_request_id != bid_request.id:
        raise ValueError("Bid does not belong to this request.")
    if bid.status != Bid.Status.PENDING:
        raise ValueError("This bid can no longer be awarded.")
    if bid.counter_status == "pending":
        raise ValueError(
            "Wait for the driver to accept or decline your counter before approving this bid."
        )

    delivery = bid_request.delivery
    driver = bid.driver
    vehicle = getattr(driver, "assigned_vehicle", None)

    bid.status = Bid.Status.ACCEPTED
    bid.save(update_fields=["status"])

    bid_request.bids.exclude(pk=bid.pk).filter(status=Bid.Status.PENDING).update(
        status=Bid.Status.REJECTED
    )
    bid_request.status = BidRequest.Status.AWARDED
    bid_request.winning_bid = bid
    bid_request.save(update_fields=["status", "winning_bid"])

    delivery.assigned_driver = driver
    delivery.assigned_vehicle = vehicle
    delivery.fare = bid.amount
    delivery.status = Delivery.Status.PENDING_DRIVER_RESPONSE
    delivery.latest_note = (
        f"Bid awarded to {driver.get_full_name().strip() or driver.email}. "
        f"Waiting for driver to accept ({bid.distance_km} km, {bid.weight_kg} kg)."
    )
    delivery.save(
        update_fields=[
            "assigned_driver",
            "assigned_vehicle",
            "fare",
            "status",
            "latest_note",
            "updated_at",
        ],
    )

    DeliveryEvent.objects.create(
        delivery=delivery,
        actor=awarded_by,
        event_type=DeliveryEvent.EventType.ASSIGNED,
        message=f"Customer awarded bid from {driver.get_full_name().strip() or driver.email}.",
    )
    create_notification(
        driver,
        "Bid won",
        f"Your bid of {bid.amount} ETB was accepted for {delivery.public_id}. Please accept the delivery.",
        delivery,
        notification_type=Notification.Type.BID_AWARDED,
        bid_request=bid_request,
        bid=bid,
        link_path="/driver",
    )
    for rejected in bid_request.bids.filter(status=Bid.Status.REJECTED).select_related(
        "driver"
    ):
        create_notification(
            rejected.driver,
            "Bid not selected",
            f"Another driver was selected for {delivery.public_id}.",
            delivery,
            notification_type=Notification.Type.BID_LOST,
            bid_request=bid_request,
            bid=bid,
            link_path="/driver/bidding",
        )

    return delivery


def cancel_bid_request(bid_request, cancelled_by):
    if bid_request.status != BidRequest.Status.OPEN:
        raise ValueError("This bidding request is no longer open.")

    delivery = bid_request.delivery
    bid_request.status = BidRequest.Status.CANCELLED
    bid_request.save(update_fields=["status"])

    bid_request.bids.filter(status=Bid.Status.PENDING).update(
        status=Bid.Status.REJECTED
    )

    delivery.status = Delivery.Status.CANCELLED
    delivery.latest_note = "Bidding cancelled by customer."
    delivery.save(update_fields=["status", "latest_note", "updated_at"])

    DeliveryEvent.objects.create(
        delivery=delivery,
        actor=cancelled_by,
        event_type=DeliveryEvent.EventType.NOTE,
        message="Customer cancelled open bidding.",
    )

    from bidding.bidding_notify import notify_bidding_cancelled

    notify_bidding_cancelled(bid_request)
    return bid_request
