from decimal import Decimal

from django.utils import timezone

from .models import Coupon


class CouponError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


def normalize_code(code):
    return (code or '').strip().upper()


def normalize_phone(phone):
    digits = ''.join(ch for ch in str(phone or '') if ch.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def phones_match(left, right):
    a = normalize_phone(left)
    b = normalize_phone(right)
    return bool(a and b and a == b)


def normalize_service_ids(service_ids=None, priced_rows=None):
    ids = set()
    if priced_rows:
        for row in priced_rows:
            sid = row.get('service_id')
            if sid is not None and str(sid).isdigit():
                ids.add(int(sid))
    if service_ids:
        for sid in service_ids:
            if sid is not None and str(sid).isdigit():
                ids.add(int(sid))
    return ids


def discountable_amount(coupon, subtotal, priced_rows=None, service_ids=None):
    """
    Amount the coupon discount is calculated against.
    Service-restricted coupons apply only to matching line items.
    """
    subtotal = Decimal(subtotal or 0)
    if not coupon.service_id:
        return subtotal

    target_id = int(coupon.service_id)
    if priced_rows:
        amount = sum(
            (Decimal(row['price']) for row in priced_rows if int(row.get('service_id') or 0) == target_id),
            Decimal('0.00'),
        )
        return amount

    selected = normalize_service_ids(service_ids=service_ids)
    if target_id in selected:
        # Without priced rows we cannot isolate the line price safely.
        return Decimal('0.00')
    return Decimal('0.00')


def get_coupon_by_code(code):
    normalized = normalize_code(code)
    if not normalized:
        return None
    return Coupon.objects.select_related('service').filter(code__iexact=normalized).first()


def validate_and_apply_coupon(
    code,
    subtotal,
    customer_phone=None,
    now=None,
    priced_rows=None,
    service_ids=None,
):
    """
    Validate a coupon against a cart and optional customer phone.
    Returns (coupon, discount_amount) or raises CouponError.
    """
    normalized = normalize_code(code)
    if not normalized:
        raise CouponError('Please enter a coupon code.')

    coupon = get_coupon_by_code(normalized)
    if not coupon:
        raise CouponError('Invalid coupon code.')

    now = now or timezone.now()
    if not coupon.is_active:
        raise CouponError('This coupon is no longer active.')
    if coupon.valid_from and now < coupon.valid_from:
        raise CouponError('This coupon is not valid yet.')
    if coupon.valid_until and now > coupon.valid_until:
        raise CouponError('This coupon has expired.')

    if coupon.customer_phone:
        phone = normalize_phone(customer_phone)
        if not phone:
            raise CouponError('Enter your mobile number to use this coupon.')
        if not phones_match(coupon.customer_phone, phone):
            raise CouponError('This coupon is not valid for your mobile number.')

    selected_ids = normalize_service_ids(service_ids=service_ids, priced_rows=priced_rows)
    if coupon.service_id:
        service_name = coupon.service.name if coupon.service else 'the selected service'
        if int(coupon.service_id) not in selected_ids:
            raise CouponError(f'This coupon is only valid for {service_name}.')

    base_amount = discountable_amount(
        coupon,
        subtotal,
        priced_rows=priced_rows,
        service_ids=service_ids,
    )
    if base_amount <= 0:
        if coupon.service_id:
            service_name = coupon.service.name if coupon.service else 'the selected service'
            raise CouponError(f'This coupon is only valid for {service_name}.')
        raise CouponError('Coupon cannot be applied to this order.')

    if coupon.discount_type == Coupon.DISCOUNT_PERCENTAGE:
        if coupon.discount_value <= 0 or coupon.discount_value > 100:
            raise CouponError('This coupon is misconfigured. Please contact the salon.')
    elif coupon.discount_value <= 0:
        raise CouponError('This coupon is misconfigured. Please contact the salon.')

    discount = coupon.calculate_discount(base_amount)
    if discount <= 0:
        raise CouponError('This coupon does not apply a discount to your order.')

    return coupon, discount


def get_eligible_coupons(customer_phone=None, subtotal=None, now=None, priced_rows=None, service_ids=None):
    """
    Return currently usable coupons for a customer/cart.
    General coupons (no assigned phone/service) are included when active/valid.
    Restricted coupons are included only when the cart/customer matches.
    """
    now = now or timezone.now()
    phone = normalize_phone(customer_phone)
    subtotal = Decimal(subtotal) if subtotal is not None else None
    selected_ids = normalize_service_ids(service_ids=service_ids, priced_rows=priced_rows)

    coupons = Coupon.objects.select_related('service').filter(is_active=True).order_by('code')
    eligible = []

    for coupon in coupons:
        if coupon.valid_from and now < coupon.valid_from:
            continue
        if coupon.valid_until and now > coupon.valid_until:
            continue

        if coupon.customer_phone:
            if not phone or not phones_match(coupon.customer_phone, phone):
                continue

        if coupon.service_id and int(coupon.service_id) not in selected_ids:
            continue

        discount = Decimal('0.00')
        if subtotal is not None and subtotal > 0:
            base_amount = discountable_amount(
                coupon,
                subtotal,
                priced_rows=priced_rows,
                service_ids=service_ids,
            )
            if base_amount <= 0:
                continue
            discount = coupon.calculate_discount(base_amount)
            if discount <= 0:
                continue

        if coupon.discount_type == Coupon.DISCOUNT_PERCENTAGE:
            discount_label = f'{coupon.discount_value}% off'
        else:
            discount_label = f'₹{coupon.discount_value} off'

        if coupon.service_id and coupon.service:
            discount_label = f'{discount_label} on {coupon.service.name}'

        eligible.append({
            'code': coupon.code,
            'discount_type': coupon.discount_type,
            'discount_value': str(coupon.discount_value),
            'discount_label': discount_label,
            'discount_amount': f'{discount:.2f}' if subtotal is not None else None,
            'customer_specific': bool(coupon.customer_phone),
            'service_specific': bool(coupon.service_id),
            'service_name': coupon.service.name if coupon.service_id and coupon.service else '',
        })

    # Best savings first when subtotal is known
    if subtotal is not None:
        eligible.sort(key=lambda item: (Decimal(item['discount_amount'] or 0), item['code']), reverse=True)
    return eligible


def serialize_eligible_coupons(coupons):
    return list(coupons)


def group_pricing(group_bookings):
    """Return subtotal, discount (once per group), and payable total."""
    bookings = list(group_bookings)
    subtotal = sum((b.line_price for b in bookings), Decimal('0.00'))
    discount = Decimal('0.00')
    for booking in bookings:
        if booking.discount_amount and booking.discount_amount > discount:
            discount = booking.discount_amount
    payable = subtotal - discount
    if payable < 0:
        payable = Decimal('0.00')
    return subtotal, discount, payable
