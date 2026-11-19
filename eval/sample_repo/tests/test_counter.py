from shop.counter import Counter, IdGenerator


def test_counter():
    c = Counter()
    c.increment()
    assert c.increment(2) == 3


def test_ids():
    g = IdGenerator()
    assert [g.next_id(), g.next_id()] == [1, 2]
