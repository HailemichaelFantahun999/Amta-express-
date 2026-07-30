from decimal import Decimal
from django.utils import timezone

from fares.fare_utils import calculate_bid_amount
from bidding.models import Bid, BidNegotiation, BidRequest


def _validate_unit_price(category, bid_method, unit_price):
    if bid_method == "km" and unit_price < category.per_km_rate:
        raise ValueError(f"Per km price cannot be lower than {category.per_km_rate}.")
    if bid_method == "kg" and unit_price < category.per_kg_rate:
        raise ValueError(f"Per kg price cannot be lower than {category.per_kg_rate}.")


def record_negotiation(bid, actor, party, bid_method, unit_price, amount, message=""):
    return BidNegotiation.objects.create(
        bid_request=bid.bid_request,
        bid=bid,
        actor=actor,
        party=party,
        bid_method=bid_method,
        unit_price=unit_price,
        amount=amount,
        message=message or "",
    )


def customer_counter_bid(bid, customer, unit_price, message=""):
    if bid.bid_request.status != BidRequest.Status.OPEN:
        raise ValueError("This bidding request is no longer open.")
    if bid.bid_request.customer_id != customer.id:
        raise ValueError("Only the customer can counter this bid.")
    if bid.status != Bid.Status.PENDING:
        raise ValueError("This bid is no longer open for negotiation.")

    category = bid.bid_request.category
    bid_method = bid.bid_method
    unit_price = Decimal(unit_price)
    _validate_unit_price(category, bid_method, unit_price)

    amount = calculate_bid_amount(
        category,
        bid_method,
        unit_price,
        bid.distance_km,
        bid.weight_kg,
    )

    bid.counter_unit_price = unit_price
    bid.counter_amount = amount
    bid.counter_message = message or ""
    bid.counter_status = "pending"
    bid.counter_at = timezone.now()
    bid.save(
        update_fields=[
            "counter_unit_price",
            "counter_amount",
            "counter_message",
            "counter_status",
            "counter_at",
            "updated_at",
        ],
    )

    record_negotiation(
        bid,
        customer,
        BidNegotiation.Party.CUSTOMER,
        bid_method,
        unit_price,
        amount,
        message or "Counter offer",
    )
    return bid


def driver_accept_counter(bid, driver):
    if bid.driver_id != driver.id:
        raise ValueError("Only the bidding driver can accept this counter.")
    if bid.counter_status != "pending":
        raise ValueError("No pending counter offer to accept.")
    if bid.bid_request.status != BidRequest.Status.OPEN:
        raise ValueError("This bidding request is no longer open.")

    bid.unit_price = bid.counter_unit_price
    bid.amount = bid.counter_amount
    bid.message = bid.counter_message or bid.message
    bid.counter_status = "accepted"
    bid.save(
        update_fields=[
            "unit_price",
            "amount",
            "message",
            "counter_status",
            "updated_at",
        ],
    )

    record_negotiation(
        bid,
        driver,
        BidNegotiation.Party.DRIVER,
        bid.bid_method,
        bid.unit_price,
        bid.amount,
        "Accepted customer counter",
    )
    return bid


def driver_decline_counter(bid, driver):
    if bid.driver_id != driver.id:
        raise ValueError("Only the bidding driver can decline this counter.")
    if bid.counter_status != "pending":
        raise ValueError("No pending counter offer to decline.")

    bid.counter_status = "declined"
    bid.save(update_fields=["counter_status", "updated_at"])
    record_negotiation(
        bid,
        driver,
        BidNegotiation.Party.DRIVER,
        bid.bid_method,
        bid.unit_price,
        bid.amount,
        "Declined counter — awaiting new driver price",
    )
    return bid
