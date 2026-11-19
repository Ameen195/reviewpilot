from shop.cache import TTLCache


def test_set_get():
    c = TTLCache()
    c.set("a", 1)
    assert c.get("a") == 1
    assert c.get("missing", 0) == 0


def test_evicts_oldest():
    c = TTLCache(max_items=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)
    assert len(c) == 2
    assert c.get("a") is None
