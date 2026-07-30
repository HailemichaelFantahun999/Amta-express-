from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")


def _quantize(value):
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _reference(value, default):
    ref = Decimal(value or 0)
    return ref if ref > 0 else Decimal(default)


def min_per_km_rate(km_base, km_reference, default_reference=100):
    ref = _reference(km_reference, default_reference)
    return _quantize(Decimal(km_base) / ref)


def min_per_kg_rate(kg_base, kg_reference, default_reference=200):
    ref = _reference(kg_reference, default_reference)
    return _quantize(Decimal(kg_base) / ref)


def sync_category_rates(category):
    category.per_km_rate = min_per_km_rate(
        category.base_fare,
        getattr(category, "km_reference", None),
    )
    category.per_kg_rate = min_per_kg_rate(
        category.kg_base,
        getattr(category, "kg_reference", None),
    )


def sync_fare_settings_rates(settings_obj):
    settings_obj.per_km_rate = min_per_km_rate(
        settings_obj.base_fare,
        getattr(settings_obj, "km_reference", None),
    )
    settings_obj.per_kg_rate = min_per_kg_rate(
        settings_obj.kg_base,
        getattr(settings_obj, "kg_reference", None),
    )


def get_bidding_radius_km(category=None):
    from fares.models import FareSettings

    if category is not None:
        override = getattr(category, "bidding_radius_km", None)
        if override is not None and Decimal(override) > 0:
            return float(override)
    settings = FareSettings.get_solo()
    radius = getattr(settings, "bidding_radius_km", None)
    if radius is not None and Decimal(radius) > 0:
        return float(radius)
    return 5.0


def calculate_bid_amount(category, bid_method, unit_price, distance_km, weight_kg):
    if not category:
        return Decimal("0")
    unit_price = Decimal(unit_price)
    if bid_method == "km":
        total = Decimal(distance_km) * unit_price
        minimum = Decimal(category.base_fare)
    elif bid_method == "kg":
        total = Decimal(weight_kg) * unit_price
        minimum = Decimal(category.kg_base)
    else:
        return Decimal("0")
    if total < minimum:
        total = minimum
    return total.quantize(TWOPLACES)
