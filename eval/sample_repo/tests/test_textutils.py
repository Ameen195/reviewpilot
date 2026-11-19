from shop.textutils import chunk, initials, slugify, truncate, word_count


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"


def test_truncate():
    assert truncate("hello", 5) == "hello"
    assert truncate("hello world", 8) == "hello..."


def test_word_count():
    assert word_count("a b  c") == 3


def test_chunk():
    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_initials():
    assert initials("ada  lovelace") == "AL"
