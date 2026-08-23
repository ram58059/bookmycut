from decimal import Decimal

from .models import ComboOffer, Service


def _selected_service_objects(selected_service_ids):
    unique = Service.objects.filter(id__in=set(selected_service_ids))
    service_dict = {str(s.id): s for s in unique}
    return [service_dict[str(sid)] for sid in selected_service_ids if str(sid) in service_dict]


def active_combo_offers():
    return (
        ComboOffer.objects.filter(is_active=True)
        .select_related('linked_service')
        .prefetch_related('trigger_services')
        .order_by('sort_order', 'name')
    )


def selection_matches_triggers(selected_services, trigger_services):
    selected_ids = {s.id for s in selected_services}
    return any(t.id in selected_ids for t in trigger_services)


def selection_has_any_combo_trigger(selected_services):
    """True if any active combo offer is unlocked by the current selection."""
    if not selected_services:
        return False
    selected_ids = {s.id for s in selected_services}
    return ComboOffer.objects.filter(
        is_active=True,
        trigger_services__id__in=selected_ids,
    ).exists()


def get_combo_price_map(selected_service_ids=None):
    """
    Map linked_service_id -> combo Decimal for active offers unlocked by
    the current selection. If selected_service_ids is None, all active offers.
    """
    offers = active_combo_offers()
    selected_ids = None
    if selected_service_ids is not None:
        selected_ids = {int(sid) for sid in selected_service_ids if str(sid).isdigit()}

    price_map = {}
    for offer in offers:
        if selected_ids is not None:
            trigger_ids = {t.id for t in offer.trigger_services.all()}
            if not (trigger_ids & selected_ids):
                continue
        price_map[str(offer.linked_service_id)] = Decimal(offer.combo_price)
    return price_map


def sync_combo_overrides(selected_service_ids, services=None):
    """
    If a trigger service is selected alongside a combo-linked service,
    store combo price overrides for the session.
    """
    if not selected_service_ids:
        return {}

    if services is None:
        services = _selected_service_objects(selected_service_ids)

    if not selection_has_any_combo_trigger(services):
        return {}

    combo_map = get_combo_price_map(selected_service_ids)
    overrides = {}
    for sid in selected_service_ids:
        key = str(sid)
        if key in combo_map:
            overrides[key] = f'{combo_map[key]:.2f}'
    return overrides


def line_price_for_service(service, overrides=None):
    overrides = overrides or {}
    key = str(service.id)
    if key in overrides:
        return Decimal(str(overrides[key]))
    return Decimal(service.price)


def build_priced_services(selected_service_ids, overrides=None):
    overrides = overrides or {}
    unique = Service.objects.filter(id__in=set(selected_service_ids))
    service_dict = {str(s.id): s for s in unique}
    combo_map = get_combo_price_map(selected_service_ids)
    # Also look up original prices from ComboOffer when available
    offer_originals = {
        str(o.linked_service_id): Decimal(o.original_price)
        for o in active_combo_offers()
    }

    rows = []
    for sid in selected_service_ids:
        service = service_dict.get(str(sid))
        if not service:
            continue
        key = str(service.id)
        price = line_price_for_service(service, overrides)
        regular = offer_originals.get(key, Decimal(service.price))
        is_combo = key in overrides and key in combo_map
        rows.append({
            'service': service,
            'service_id': service.id,
            'name': service.name,
            'price': price,
            'regular_price': regular,
            'is_combo': is_combo,
            'savings': (regular - price) if is_combo and regular > price else Decimal('0.00'),
        })
    return rows


def cart_subtotal(selected_service_ids, overrides=None):
    return sum(
        (row['price'] for row in build_priced_services(selected_service_ids, overrides)),
        Decimal('0.00'),
    )


def get_upsell_carousel_items(selected_service_ids, overrides=None):
    """Build carousel cards for active combos unlocked by the current selection."""
    overrides = overrides or {}
    selected = _selected_service_objects(selected_service_ids)
    if not selected:
        return []

    selected_ids = {str(sid) for sid in selected_service_ids}
    selected_service_id_set = {s.id for s in selected}
    cards = []
    accent_cycle = [
        ('from-fuchsia-600 via-rose-500 to-orange-400', 'bg-fuchsia-500'),
        ('from-cyan-600 via-sky-500 to-indigo-500', 'bg-cyan-500'),
        ('from-emerald-600 via-teal-500 to-lime-400', 'bg-emerald-500'),
        ('from-violet-700 via-purple-500 to-pink-500', 'bg-violet-500'),
        ('from-amber-500 via-orange-500 to-rose-500', 'bg-amber-500'),
        ('from-blue-700 via-indigo-500 to-cyan-400', 'bg-blue-500'),
        ('from-rose-600 via-red-500 to-orange-400', 'bg-rose-500'),
        ('from-teal-700 via-emerald-500 to-cyan-400', 'bg-teal-500'),
    ]

    for index, offer in enumerate(active_combo_offers()):
        trigger_ids = {t.id for t in offer.trigger_services.all()}
        if not (trigger_ids & selected_service_id_set):
            continue

        service = offer.linked_service
        regular = Decimal(offer.original_price)
        combo = Decimal(offer.combo_price)
        savings = offer.savings
        already_added = str(service.id) in selected_ids
        gradient, badge_bg = accent_cycle[index % len(accent_cycle)]

        cards.append({
            'offer_id': offer.id,
            'service_id': service.id,
            'name': offer.name,
            'tagline': offer.description or 'Upgrade your appointment with this exclusive combo rate.',
            'description': (getattr(service, 'description', '') or offer.description or '').strip(),
            'badge': offer.badge_text or 'Combo Deal',
            'regular_price': regular,
            'combo_price': combo,
            'savings': savings,
            'image_url': offer.display_image_url(),
            'duration_minutes': offer.duration_minutes or service.duration_minutes,
            'already_added': already_added,
            'gradient': gradient,
            'badge_bg': badge_bg,
        })
    return cards


def get_offer_for_linked_service(service_id, selected_service_ids):
    """Return the active ComboOffer for a linked service if unlocked by selection."""
    selected_ids = {int(sid) for sid in selected_service_ids if str(sid).isdigit()}
    for offer in active_combo_offers().filter(linked_service_id=service_id):
        trigger_ids = {t.id for t in offer.trigger_services.all()}
        if trigger_ids & selected_ids:
            return offer
    return None
