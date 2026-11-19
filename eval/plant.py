# ruff: noqa: ISC004 - edits are written as concatenated literals on purpose
"""Planted-bug dataset. Ground truth comes from this file only, never from the model.

Each PR is a set of exact text edits on eval/sample_repo. The planted bug's line is found by a
marker substring in the new file, so line numbers never drift by hand.

    uv run python eval/plant.py          # writes eval/dataset.json
    uv run python eval/plant.py --show 10  # prints a mixed sample for checking
"""

import difflib
import json
import sys
from pathlib import Path

REPO = Path(__file__).parent / "sample_repo"
DATASET = Path(__file__).parent / "dataset.json"

# Which reviewer should own each bug type (findings only carry the reviewer name).
EXPECTED_REVIEWER = {
    "off_by_one": "bug", "missing_null": "bug", "race_condition": "bug", "logic": "bug",
    "resource_leak": "bug", "sql_injection": "security", "hardcoded_secret": "security",
    "missing_test": "tests", "clean": None,
}  # fmt: skip


def P(id, cat, title, bug, file, edits, mark=None, also=None):
    """edits: [(old, new)] on `file` (old=None means a new file). also: {path: edits}."""
    return {"id": id, "category": cat, "title": title, "bug": bug, "file": file,
            "edits": {file: edits, **(also or {})}, "mark": mark}  # fmt: skip


PRS = [
    # ---- off-by-one ----
    P(
        "ob1",
        "off_by_one",
        "Simplify moving_average loop",
        "range stops one window early, last average is dropped",
        "shop/stats.py",
        [("range(len(xs) - window + 1)", "range(len(xs) - window)")],
        "range(len(xs) - window)",
    ),
    P(
        "ob2",
        "off_by_one",
        "Tidy paginate",
        "pages are 1-based but start no longer subtracts 1, page 1 skips the first page",
        "shop/orders.py",
        [("start = (page - 1) * per_page", "start = page * per_page")],
        "start = page * per_page",
    ),
    P(
        "ob3",
        "off_by_one",
        "Fix truncate cutting too much",
        "+1 makes the result one character longer than limit",
        "shop/textutils.py",
        [("text[: limit - len(suffix)]", "text[: limit - len(suffix) + 1]")],
        "limit - len(suffix) + 1",
    ),
    P(
        "ob4",
        "off_by_one",
        "Add bottom_n helper",
        "slice [:n - 1] returns n-1 items",
        "shop/stats.py",
        [("def clamp(", "def bottom_n(xs, n):\n    return sorted(xs)[: n - 1]\n\n\ndef clamp(")],
        "sorted(xs)[: n - 1]",
    ),
    P(
        "ob5",
        "off_by_one",
        "chunk: avoid empty trailing chunk",
        "range end len(items) - 1 drops the last item when len % size == 1",
        "shop/textutils.py",
        [("range(0, len(items), size)", "range(0, len(items) - 1, size)")],
        "len(items) - 1",
        also={
            "tests/test_textutils.py": [
                (
                    "def test_initials",
                    "def test_chunk_odd():\n    assert chunk([1, 2, 3], 2) == "
                    "[[1, 2], [3]]\n\n\ndef test_initials",
                )
            ]
        },
    ),
    # ---- missing null check ----
    P(
        "mn1",
        "missing_null",
        "Simplify get_user",
        "unpacks fetchone() directly, crashes with TypeError for an unknown id",
        "shop/users_db.py",
        [
            (
                '    row = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))'
                ".fetchone()\n    if row is None:\n        return None\n"
                '    return {"id": row[0], "name": row[1], "email": row[2]}',
                "    id_, name, email = conn.execute(\n"
                '        "SELECT id, name, email FROM users WHERE id = ?", (user_id,)\n    ).fetchone()\n'
                '    return {"id": id_, "name": name, "email": email}',
            )
        ],
        "id_, name, email = conn.execute(",
    ),
    P(
        "mn2",
        "missing_null",
        "Add coupon_code helper",
        "coupon is Optional, .upper() on None raises AttributeError",
        "shop/orders.py",
        [
            (
                "def find_order(",
                "def coupon_code(order):\n    return order.coupon.upper()\n\n\ndef find_order(",
            )
        ],
        "order.coupon.upper()",
        also={
            "tests/test_orders.py": [
                ("from shop.orders import Order,", "from shop.orders import Order, coupon_code,"),
                (
                    "def test_free_shipping",
                    "def test_coupon_code():\n    assert coupon_code(Order(1, "
                    "coupon='off10')) == 'OFF10'\n    assert coupon_code(Order(2)) is None\n\n\n"
                    "def test_free_shipping",
                ),
            ]
        },
    ),
    P(
        "mn3",
        "missing_null",
        "Add item count lookup",
        "find_order returns None for an unknown id, .items then crashes",
        "shop/orders.py",
        [
            (
                "def is_free_shipping(",
                "def item_count(orders, order_id):\n"
                "    return len(find_order(orders, order_id).items)\n\n\ndef is_free_shipping(",
            )
        ],
        "find_order(orders, order_id).items",
    ),
    P(
        "mn4",
        "missing_null",
        "Strip whitespace from API key",
        "os.environ.get may return None, .strip() crashes and the clear error is gone",
        "shop/config.py",
        [
            (
                '    key = os.environ.get("SHOP_API_KEY")\n    if not key:\n'
                '        raise RuntimeError("SHOP_API_KEY is not set")\n    return key',
                '    return os.environ.get("SHOP_API_KEY").strip()',
            )
        ],
        'os.environ.get("SHOP_API_KEY").strip()',
    ),
    P(
        "mn5",
        "missing_null",
        "Streamline cache get",
        "unpacks dict.get() result, a missing key raises TypeError instead of returning default",
        "shop/cache.py",
        [
            (
                "            item = self._data.get(key)\n            if item is None:\n"
                "                return default\n            value, expires = item\n",
                "            value, expires = self._data.get(key)\n",
            )
        ],
        "value, expires = self._data.get(key)",
    ),
    # ---- SQL injection ----
    P(
        "sq1",
        "sql_injection",
        "Simplify email lookup query",
        "email is interpolated into the SQL string",
        "shop/users_db.py",
        [
            (
                'conn.execute("SELECT id, name FROM users WHERE email = ?", (email,))',
                "conn.execute(f\"SELECT id, name FROM users WHERE email = '{email}'\")",
            )
        ],
        "WHERE email = '{email}'",
    ),
    P(
        "sq2",
        "sql_injection",
        "delete_user: build query inline",
        "user_id is concatenated into a DELETE statement",
        "shop/users_db.py",
        [
            (
                'conn.execute("DELETE FROM users WHERE id = ?", (user_id,))',
                'conn.execute("DELETE FROM users WHERE id = " + str(user_id))',
            )
        ],
        '"DELETE FROM users WHERE id = " + str(user_id)',
    ),
    P(
        "sq3",
        "sql_injection",
        "Add user search",
        "search term concatenated into a LIKE clause",
        "shop/users_db.py",
        [
            (
                "def count_users(",
                "def search_users(conn, term):\n"
                '    sql = "SELECT id, name FROM users WHERE name LIKE \'%" + term + "%\'"\n'
                "    return conn.execute(sql).fetchall()\n\n\ndef count_users(",
            )
        ],
        "LIKE '%\" + term",
    ),
    P(
        "sq4",
        "sql_injection",
        "Allow sorting users by column",
        "caller-controlled column name goes straight into ORDER BY",
        "shop/users_db.py",
        [
            (
                "def count_users(",
                "def users_sorted(conn, column):\n"
                '    return conn.execute(f"SELECT id, name, email FROM users ORDER BY {column}").fetchall()'
                "\n\n\ndef count_users(",
            )
        ],
        "ORDER BY {column}",
    ),
    P(
        "sq5",
        "sql_injection",
        "get_user: use string formatting",
        "user_id %-formatted into the query",
        "shop/users_db.py",
        [
            (
                'conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))',
                'conn.execute("SELECT id, name, email FROM users WHERE id = %s" % user_id)',
            )
        ],
        'WHERE id = %s" % user_id',
    ),
    # ---- hardcoded secret ----
    P(
        "hs1",
        "hardcoded_secret",
        "Default API key for local dev",
        "API key hardcoded as the default",
        "shop/config.py",
        [
            (
                '    key = os.environ.get("SHOP_API_KEY")\n',
                '    key = os.environ.get("SHOP_API_KEY", "shoplive-0000-1111-2222-3333")\n',
            )
        ],
        "shoplive-0000-1111-2222-3333",
    ),
    P(
        "hs2",
        "hardcoded_secret",
        "Point default DB at the shared server",
        "production DB password in the default URL",
        "shop/config.py",
        [('"sqlite:///shop.db"', '"postgresql://admin:hunter2-prod@db.prod.internal:5432/shop"')],
        "hunter2-prod",
    ),
    P(
        "hs3",
        "hardcoded_secret",
        "Add payments module",
        "Stripe secret key committed in source",
        "shop/payments.py",
        [
            (
                None,
                'STRIPE_SECRET = "stripe-secret-0000-1111-2222"\n\n\n'
                "def charge_headers():\n"
                '    return {"Authorization": f"Bearer {STRIPE_SECRET}"}\n',
            )
        ],
        "STRIPE_SECRET = ",
    ),
    P(
        "hs4",
        "hardcoded_secret",
        "Add S3 upload settings",
        "AWS access key pair hardcoded",
        "shop/config.py",
        [
            (
                "DEFAULTS = {",
                'AWS_ACCESS_KEY_ID = "ACCESSKEY-0000-1111"\n'
                'AWS_SECRET_ACCESS_KEY = "secretkey-0000-1111-2222-3333"\n\nDEFAULTS = {',
            )
        ],
        "AWS_SECRET_ACCESS_KEY = ",
    ),
    P(
        "hs5",
        "hardcoded_secret",
        "Upload reports to the dashboard",
        "GitHub token hardcoded in the request headers",
        "shop/files.py",
        [
            (
                "def file_size(",
                "def upload_headers():\n"
                '    return {"Authorization": "Bearer dashtoken-0000-1111-2222-3333"}'
                "\n\n\ndef file_size(",
            )
        ],
        "dashtoken-0000-1111-2222-3333",
    ),
    # ---- race condition ----
    P(
        "rc1",
        "race_condition",
        "Counter: drop lock for speed",
        "+= on shared state without the lock loses updates across threads",
        "shop/counter.py",
        [
            (
                "        with self._lock:\n            self._value += n\n            return self._value",
                "        self._value += n\n        return self._value",
            )
        ],
        "        self._value += n",
    ),
    P(
        "rc2",
        "race_condition",
        "Simplify next_id",
        "read-then-write of _next without the lock can hand out duplicate ids",
        "shop/counter.py",
        [
            (
                "        with self._lock:\n            i = self._next\n            self._next += 1\n"
                "            return i",
                "        i = self._next\n        self._next = i + 1\n        return i",
            )
        ],
        "        i = self._next",
    ),
    P(
        "rc3",
        "race_condition",
        "cache.set: hold the lock for less time",
        "eviction check and delete run outside the lock",
        "shop/cache.py",
        [
            (
                "        with self._lock:\n            if len(self._data) >= self.max_items and key not in"
                " self._data:\n                oldest = min(self._data, key=lambda k: self._data[k][1])\n"
                "                del self._data[oldest]\n            self._data[key]",
                "        if len(self._data) >= self.max_items and key not in self._data:\n"
                "            oldest = min(self._data, key=lambda k: self._data[k][1])\n"
                "            del self._data[oldest]\n        with self._lock:\n            self._data[key]",
            )
        ],
        "        if len(self._data) >= self.max_items",
    ),
    P(
        "rc4",
        "race_condition",
        "Add RateLimiter for API calls",
        "check-then-increment of used is not under the lock it creates",
        "shop/counter.py",
        [(None, None)],
        "        if self.used < self.limit:",
    ),
    P(
        "rc5",
        "race_condition",
        "Add add_user_unique",
        "check-then-insert with no UNIQUE constraint, two callers can both insert",
        "shop/users_db.py",
        [
            (
                "def get_user(",
                "def add_user_unique(conn, name, email):\n"
                "    if find_by_email(conn, email):\n"
                '        raise ValueError("email already registered")\n'
                "    return add_user(conn, name, email)\n\n\ndef get_user(",
            )
        ],
        "    if find_by_email(conn, email):",
    ),
    # ---- wrong operator / logic ----
    P(
        "lg1",
        "logic",
        "Free shipping from 50",
        "> instead of >=, an order of exactly 50 no longer ships free",
        "shop/orders.py",
        [("return total >= 50", "return total > 50")],
        "return total > 50",
    ),
    P(
        "lg2",
        "logic",
        "Round discount once",
        "returns the discount amount instead of the discounted total",
        "shop/orders.py",
        [("round(total * (100 - percent) / 100, 2)", "round(total * percent / 100, 2)")],
        "round(total * percent / 100, 2)",
    ),
    P(
        "lg3",
        "logic",
        "clamp: reorder min/max",
        "min/max swapped, always returns lo",
        "shop/stats.py",
        [("return max(lo, min(x, hi))", "return min(lo, max(x, hi))")],
        "return min(lo, max(x, hi))",
    ),
    P(
        "lg4",
        "logic",
        "order_total: use generator",
        "price + qty instead of price * qty",
        "shop/orders.py",
        [("sum(price * qty for", "sum(price + qty for")],
        "sum(price + qty for",
        also={
            "tests/test_orders.py": [
                (
                    "def test_paginate",
                    "def test_total_two_items():\n"
                    "    assert order_total(Order(1, [(10, 2), (5, 3)])) == 35\n\n\ndef test_paginate",
                )
            ]
        },
    ),
    P(
        "lg5",
        "logic",
        "median: avoid float noise",
        "// floors the even-length median",
        "shop/stats.py",
        [("(s[mid - 1] + s[mid]) / 2", "(s[mid - 1] + s[mid]) // 2")],
        "(s[mid - 1] + s[mid]) // 2",
        also={
            "tests/test_stats.py": [
                (
                    "def test_moving_average",
                    "def test_median_even():\n"
                    "    assert median([1, 2]) == 1.5\n\n\ndef test_moving_average",
                )
            ]
        },
    ),
    # ---- resource leak ----
    P(
        "rl1",
        "resource_leak",
        "read_lines: flatten",
        "file opened without with/close",
        "shop/files.py",
        [
            (
                '    with open(path, encoding="utf-8") as f:\n'
                '        return [line.rstrip("\\n") for line in f]',
                '    f = open(path, encoding="utf-8")\n    return [line.rstrip("\\n") for line in f]',
            )
        ],
        'f = open(path, encoding="utf-8")',
    ),
    P(
        "rl2",
        "resource_leak",
        "write_report: reuse writer",
        "file never closed, rows may not be flushed",
        "shop/files.py",
        [
            (
                '    with open(path, "w", newline="", encoding="utf-8") as f:\n'
                "        writer = csv.writer(f)\n"
                '        writer.writerow(["name", "total"])\n        writer.writerows(rows)',
                '    f = open(path, "w", newline="", encoding="utf-8")\n    writer = csv.writer(f)\n'
                '    writer.writerow(["name", "total"])\n    writer.writerows(rows)',
            )
        ],
        'f = open(path, "w"',
    ),
    P(
        "rl3",
        "resource_leak",
        "load_config one-liner",
        "json.load(open(...)) leaves the file handle open",
        "shop/config.py",
        [
            (
                '    with open(path, encoding="utf-8") as f:\n        data = json.load(f)',
                '    data = json.load(open(path, encoding="utf-8"))',
            )
        ],
        "json.load(open(",
    ),
    P(
        "rl4",
        "resource_leak",
        "Add count_in_file for reports",
        "sqlite connection opened and never closed",
        "shop/users_db.py",
        [
            (
                "def count_users(",
                "def count_in_file(path):\n    conn = sqlite3.connect(path)\n"
                '    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]\n\n\n'
                "def count_users(",
            )
        ],
        "    conn = sqlite3.connect(path)\n    return",
    ),
    P(
        "rl5",
        "resource_leak",
        "Add line_count",
        "open() in a generator, handle never closed",
        "shop/files.py",
        [
            (
                "def file_size(",
                "def line_count(path):\n"
                '    return sum(1 for _ in open(path, encoding="utf-8"))\n\n\ndef file_size(',
            )
        ],
        "sum(1 for _ in open(",
    ),
    # ---- missing test (code is correct, no test added) ----
    P(
        "mt1",
        "missing_test",
        "Add variance",
        "new variance() has no tests",
        "shop/stats.py",
        [
            (
                "def median(",
                "def variance(xs):\n    if not xs:\n        return 0.0\n    m = mean(xs)\n"
                "    return sum((x - m) ** 2 for x in xs) / len(xs)\n\n\ndef median(",
            )
        ],
        "def variance(",
    ),
    P(
        "mt2",
        "missing_test",
        "Add capitalize_words",
        "new capitalize_words() has no tests",
        "shop/textutils.py",
        [
            (
                "def word_count(",
                'def capitalize_words(text):\n    return " ".join(w.capitalize() '
                "for w in text.split())\n\n\ndef word_count(",
            )
        ],
        "def capitalize_words(",
    ),
    P(
        "mt3",
        "missing_test",
        "Count orders per coupon",
        "new coupon_counts() has no tests",
        "shop/orders.py",
        [
            (
                "def find_order(",
                "def coupon_counts(orders):\n    counts = {}\n    for o in orders:\n"
                "        if o.coupon:\n            counts[o.coupon] = counts.get(o.coupon, 0) + 1\n"
                "    return counts\n\n\ndef find_order(",
            )
        ],
        "def coupon_counts(",
    ),
    P(
        "mt4",
        "missing_test",
        "Add ensure_dir",
        "new ensure_dir() has no tests",
        "shop/files.py",
        [
            (
                "def file_size(",
                "def ensure_dir(path):\n    os.makedirs(path, exist_ok=True)\n"
                "    return path\n\n\ndef file_size(",
            )
        ],
        "def ensure_dir(",
    ),
    P(
        "mt5",
        "missing_test",
        "Counter.reset",
        "new reset() has no tests",
        "shop/counter.py",
        [
            (
                "    @property",
                "    def reset(self):\n        with self._lock:\n"
                "            self._value = 0\n\n    @property",
            )
        ],
        "    def reset(",
    ),
    # ---- clean (no bug) ----
    P(
        "c1",
        "clean",
        "Docstrings for stats",
        "",
        "shop/stats.py",
        [
            (
                "def mean(xs):\n",
                'def mean(xs):\n    """Arithmetic mean; 0.0 for an empty list."""\n',
            ),
            (
                "def top_n(xs, n):\n",
                'def top_n(xs, n):\n    """The n largest values, largest first."""\n',
            ),
        ],
    ),
    P(
        "c2",
        "clean",
        "Type hints for word_count",
        "",
        "shop/textutils.py",
        [("def word_count(text):", "def word_count(text: str) -> int:")],
    ),
    P(
        "c3",
        "clean",
        "Name the free shipping threshold",
        "",
        "shop/orders.py",
        [
            (
                "from dataclasses import dataclass, field\n",
                "from dataclasses import dataclass, field\n\nFREE_SHIPPING_MIN = 50\n",
            ),
            ("return total >= 50", "return total >= FREE_SHIPPING_MIN"),
        ],
    ),
    P(
        "c4",
        "clean",
        "Add list_users",
        "",
        "shop/users_db.py",
        [
            (
                "def count_users(",
                "def list_users(conn, limit=100):\n"
                '    rows = conn.execute("SELECT id, name FROM users ORDER BY id LIMIT ?", (limit,))'
                ".fetchall()\n"
                '    return [{"id": r[0], "name": r[1]} for r in rows]\n\n\ndef count_users(',
            )
        ],
        also={
            "tests/test_users_db.py": [
                ("get_user\n", "get_user, list_users\n"),
                (
                    "def test_find_and_delete",
                    "def test_list_users():\n    conn = connect()\n"
                    '    add_user(conn, "Ana", "a@x")\n    add_user(conn, "Bo", "b@x")\n'
                    '    assert [u["name"] for u in list_users(conn, limit=1)] == ["Ana"]\n\n\n'
                    "def test_find_and_delete",
                ),
            ]
        },
    ),
    P(
        "c5",
        "clean",
        "Reject non-positive timeouts",
        "",
        "shop/config.py",
        [
            (
                '    return int(cfg.get("timeout", DEFAULTS["timeout"]))',
                '    timeout = int(cfg.get("timeout", DEFAULTS["timeout"]))\n    if timeout <= 0:\n'
                '        raise ValueError("timeout must be positive")\n    return timeout',
            )
        ],
        also={
            "tests/test_config.py": [
                (
                    "    assert get_timeout({}) == 30\n",
                    "    assert get_timeout({}) == 30\n"
                    '    with pytest.raises(ValueError):\n        get_timeout({"timeout": 0})\n',
                )
            ]
        },
    ),
    P(
        "c6",
        "clean",
        "Add TTLCache.clear",
        "",
        "shop/cache.py",
        [
            (
                "    def __len__(self):",
                "    def clear(self):\n        with self._lock:\n"
                "            self._data.clear()\n\n    def __len__(self):",
            )
        ],
        also={"tests/test_cache.py": [(None, None)]},
    ),
    P(
        "c7",
        "clean",
        "Add Counter.decrement",
        "",
        "shop/counter.py",
        [
            (
                "    @property",
                "    def decrement(self, n=1):\n        with self._lock:\n"
                "            self._value -= n\n            return self._value\n\n    @property",
            )
        ],
        also={
            "tests/test_counter.py": [
                (
                    "    assert c.increment(2) == 3\n",
                    "    assert c.increment(2) == 3\n    assert c.decrement() == 2\n",
                )
            ]
        },
    ),
    P(
        "c8",
        "clean",
        "Configurable report header",
        "",
        "shop/files.py",
        [
            (
                "def write_report(path, rows):",
                'def write_report(path, rows, header=("name", "total")):',
            ),
            ('writer.writerow(["name", "total"])', "writer.writerow(list(header))"),
        ],
    ),
    P(
        "c9",
        "clean",
        "Use fsum in mean for precision",
        "",
        "shop/stats.py",
        [
            ("def mean(xs):", "import math\n\n\ndef mean(xs):"),
            ("return sum(xs) / len(xs)", "return math.fsum(xs) / len(xs)"),
        ],
    ),
    P(
        "c10",
        "clean",
        "Document chunk",
        "",
        "shop/textutils.py",
        [
            (
                "def chunk(items, size):\n",
                'def chunk(items, size):\n    """Split items into lists of at most `size` items."""\n',
            )
        ],
    ),
]

# Edits that are easier to write as whole new text (marked with (None, None) above).
_COUNTER_TAIL = """

class RateLimiter:
    def __init__(self, limit):
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    def allow(self):
        if self.used < self.limit:
            self.used += 1
            return True
        return False
"""
_CACHE_TEST_TAIL = """

def test_clear():
    c = TTLCache()
    c.set("a", 1)
    c.clear()
    assert len(c) == 0
"""
_APPEND = {
    ("rc4", "shop/counter.py"): _COUNTER_TAIL,
    ("c6", "tests/test_cache.py"): _CACHE_TEST_TAIL,
}


def apply(pr: dict) -> dict[str, tuple[str, str]]:
    """{path: (old_text, new_text)} for every file the PR touches."""
    out = {}
    for path, edits in pr["edits"].items():
        src = REPO / path
        old = src.read_text(encoding="utf-8") if src.exists() else ""
        new = old
        for a, b in edits:
            if a is None and b is None:
                new += _APPEND[(pr["id"], path)]
            elif a is None:
                assert not old, f"{pr['id']}: {path} already exists"
                new = b
            else:
                assert new.count(a) == 1, (
                    f"{pr['id']}: edit not found exactly once in {path}: {a!r}"
                )
                new = new.replace(a, b)
        assert new != old, f"{pr['id']}: no change in {path}"
        out[path] = (old, new)
    return out


def patch(old: str, new: str) -> str:
    """GitHub-style per-file patch: hunks only, no ---/+++ headers."""
    lines = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=3)
    return "\n".join(list(lines)[2:])


def truth_line(pr: dict, new: str) -> int | None:
    if not pr["mark"]:
        return None
    i = new.find(pr["mark"])
    assert i >= 0 and new.count(pr["mark"]) == 1, f"{pr['id']}: marker not unique: {pr['mark']!r}"
    i += len(pr["mark"]) - len(pr["mark"].lstrip("\n "))  # skip leading indent/newlines
    return new.count("\n", 0, i) + 1


def build(pr: dict) -> tuple[dict, list[dict], dict[str, str]]:
    """(pr dict, GitHub-style files list, {path: new content}) for build_context and the sandbox."""
    changed = apply(pr)
    files = [
        {"filename": p, "status": "added" if not old else "modified", "patch": patch(old, new)}
        for p, (old, new) in changed.items()
    ]
    head = {"number": 0, "title": pr["title"], "head": {"sha": pr["id"]}}
    return head, files, {p: new for p, (_, new) in changed.items()}


def interleave(prs: list[dict]) -> list[dict]:
    """Spread every category evenly over the run, so a partial run is a fair sample."""
    by_cat: dict[str, list[dict]] = {}
    for p in prs:
        by_cat.setdefault(p["category"], []).append(p)
    cats = list(by_cat)
    key = lambda p: (by_cat[p["category"]].index(p) / len(by_cat[p["category"]]),
                     cats.index(p["category"]))  # fmt: skip
    return sorted(prs, key=key)


ORDER = interleave(PRS)


def dataset() -> list[dict]:
    rows = []
    for pr in ORDER:
        _head, files, contents = build(pr)
        rows.append({
            "id": pr["id"], "category": pr["category"],
            "expected_reviewer": EXPECTED_REVIEWER[pr["category"]], "title": pr["title"],
            "bug": pr["bug"], "file": pr["file"] if pr["mark"] else None,
            "line": truth_line(pr, contents[pr["file"]]), "files": files,
        })  # fmt: skip
    return rows


def show(rows: list[dict], n: int) -> None:
    """A mixed sample: bug PRs from different categories plus 2 clean ones."""
    seen, picked = set(), []
    for r in rows:
        if r["category"] != "clean" and r["category"] not in seen:
            seen.add(r["category"])
            picked.append(r)
    picked = picked[: n - 2] + [r for r in rows if r["category"] == "clean"][:2]
    for r in picked:
        print(f'\n{r["id"]} [{r["category"]}] "{r["title"]}"')
        if r["category"] == "clean":
            print(f"  no bug; files: {', '.join(f['filename'] for f in r['files'])}")
        else:
            print(f"  {r['file']}:{r['line']} - {r['bug']}")
        for f in r["files"]:
            for line in f["patch"].splitlines():
                if line.startswith(("+", "-")):
                    print(f"    {f['filename'].split('/')[-1]}: {line}")


if __name__ == "__main__":
    rows = dataset()
    DATASET.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    counts = {c: sum(r["category"] == c for r in rows) for c in EXPECTED_REVIEWER}
    print(f"wrote {DATASET} ({len(rows)} PRs): {counts}")
    if "--show" in sys.argv:
        show(rows, int(sys.argv[sys.argv.index("--show") + 1]))
