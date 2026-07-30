from notifications.notifications_service import create_notification
from notifications.models import Notification


def _customer_link():
    return "/customer/bidding"


def _driver_link():
    return "/driver/bidding"


def notify_bidding_open(bid_request):
    delivery = bid_request.delivery
    create_notification(
        bid_request.customer,
        "Bidding started",
        f"Drivers can bid on {delivery.public_id}. You will be notified of each offer.",
        delivery=delivery,
        notification_type=Notification.Type.BIDDING_OPEN,
        bid_request=bid_request,
        link_path=_customer_link(),
    )


def notify_bid_received(bid, created=True):
    bid_request = bid.bid_request
    delivery = bid_request.delivery
    driver_name = bid.driver.get_full_name().strip() or bid.driver.email
    title = "New bid received" if created else "Bid updated"
    create_notification(
        bid_request.customer,
        title,
        f"{driver_name} offered {bid.amount} ETB on {delivery.public_id}.",
        delivery=delivery,
        notification_type=(
            Notification.Type.BID_RECEIVED if created else Notification.Type.BID_UPDATED
        ),
        bid_request=bid_request,
        bid=bid,
        link_path=_customer_link(),
    )


def notify_counter_offer(bid):
    bid_request = bid.bid_request
    delivery = bid_request.delivery
    create_notification(
        bid.driver,
        "Counter offer from customer",
        (
            f"Customer countered at {bid.counter_amount} ETB on {delivery.public_id}. "
            f"Accept or send a new price."
        ),
        delivery=delivery,
        notification_type=Notification.Type.BID_COUNTER,
        bid_request=bid_request,
        bid=bid,
        link_path=_driver_link(),
    )


def notify_counter_accepted(bid):
    bid_request = bid.bid_request
    delivery = bid_request.delivery
    driver_name = bid.driver.get_full_name().strip() or bid.driver.email
    create_notification(
        bid_request.customer,
        "Driver accepted your offer",
        f"{driver_name} accepted your counter on {delivery.public_id} ({bid.amount} ETB).",
        delivery=delivery,
        notification_type=Notification.Type.COUNTER_ACCEPTED,
        bid_request=bid_request,
        bid=bid,
        link_path=_customer_link(),
    )


def notify_bidding_cancelled(bid_request):
    delivery = bid_request.delivery
    create_notification(
        bid_request.customer,
        "Bidding cancelled",
        f"Bidding for {delivery.public_id} was cancelled. No further offers will be accepted.",
        delivery=delivery,
        notification_type=Notification.Type.GENERAL,
        bid_request=bid_request,
        link_path=_customer_link(),
    )
    for bid in bid_request.bids.select_related("driver"):
        create_notification(
            bid.driver,
            "Bidding cancelled",
            f"The customer cancelled bidding for {delivery.public_id}.",
            delivery=delivery,
            notification_type=Notification.Type.GENERAL,
            bid_request=bid_request,
            bid=bid,
            link_path=_driver_link(),
        )


def notify_counter_rejected(bid):
    bid_request = bid.bid_request
    delivery = bid_request.delivery
    driver_name = bid.driver.get_full_name().strip() or bid.driver.email
    message = (
        f"{driver_name} declined your counter on {delivery.public_id}. "
        "You can send another counter or approve the current price."
    )
    create_notification(
        bid_request.customer,
        "Driver declined your counter",
        message,
        delivery=delivery,
        notification_type=Notification.Type.COUNTER_DECLINED,
        bid_request=bid_request,
        bid=bid,
        link_path=_customer_link(),
    )


def notify_counter_declined(bid):
    bid_request = bid.bid_request
    delivery = bid_request.delivery
    driver_name = bid.driver.get_full_name().strip() or bid.driver.email
    create_notification(
        bid_request.customer,
        "Driver sent a new price",
        f"{driver_name} declined your counter and bid {bid.amount} ETB on {delivery.public_id}.",
        delivery=delivery,
        notification_type=Notification.Type.COUNTER_DECLINED,
        bid_request=bid_request,
        bid=bid,
        link_path=_customer_link(),
    )
