from dataclasses import dataclass, field


@dataclass
class Order:
    id: int
    items: list = field(default_factory=list)  # (price, qty) pairs
    coupon: str | None = None


def order_total(order):
    """Order value: each item's price times its quantity, summed."""
    return sum(price * qty for price, qty in order.items)


def apply_discount(total, percent):
    """The total left to pay after taking `percent` % off."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(total * (100 - percent) / 100, 2)


def paginate(items, page, per_page):
    """Items on `page`; pages are numbered from 1."""
    start = (page - 1) * per_page
    return items[start : start + per_page]


def find_order(orders, order_id):
    for o in orders:
        if o.id == order_id:
            return o
    return None


def is_free_shipping(total):
    """Orders of 50 or more ship free."""
    return total >= 50
