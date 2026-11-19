import threading


class Inventory:
    """Stock levels per SKU. Safe to use from several threads."""

    def __init__(self):
        self._stock = {}
        self._lock = threading.Lock()

    def add(self, sku, qty):
        with self._lock:
            self._stock[sku] = self._stock.get(sku, 0) + qty

    def reserve(self, sku, qty):
        """Take qty out of stock; returns False (and changes nothing) if there is not enough."""
        with self._lock:
            have = self._stock.get(sku, 0)
            if have < qty:
                return False
            self._stock[sku] = have - qty
            return True

    def level(self, sku):
        with self._lock:
            return self._stock.get(sku, 0)


def low_stock(levels, threshold):
    """SKUs whose level is at or below threshold, sorted by SKU."""
    return sorted(sku for sku, n in levels.items() if n <= threshold)


def restock_amount(level, target):
    """How many units to order to reach target; never negative."""
    return max(target - level, 0)
