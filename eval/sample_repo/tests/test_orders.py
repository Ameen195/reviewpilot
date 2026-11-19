from shop.orders import Order, apply_discount, find_order, is_free_shipping, order_total, paginate


def test_total_and_discount():
    assert order_total(Order(1, [(10, 2)])) == 20
    assert apply_discount(200, 10) == 180


def test_paginate():
    assert paginate([1, 2, 3, 4, 5], 1, 2) == [1, 2]
    assert paginate([1, 2, 3, 4, 5], 3, 2) == [5]


def test_find_order():
    assert find_order([Order(1)], 2) is None


def test_free_shipping():
    assert is_free_shipping(50)
    assert not is_free_shipping(49.99)
