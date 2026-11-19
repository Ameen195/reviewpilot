import pytest
from shop.stats import clamp, mean, median, moving_average, top_n


def test_mean():
    assert mean([1, 2, 3]) == 2
    assert mean([]) == 0.0


def test_median():
    assert median([3, 1, 2]) == 2
    with pytest.raises(ValueError):
        median([])


def test_moving_average():
    assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]


def test_top_n():
    assert top_n([5, 1, 9, 3], 2) == [9, 5]


def test_clamp():
    assert clamp(5, 0, 3) == 3
    assert clamp(-1, 0, 3) == 0
