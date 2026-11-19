from datetime import timedelta


def business_days(start, days):
    """The next `days` weekdays (Mon-Fri) after start, in order."""
    out = []
    d = start
    while len(out) < days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def overlaps(a_start, a_end, b_start, b_end):
    """True if the half-open ranges [a_start, a_end) and [b_start, b_end) share any time."""
    return a_start < b_end and b_start < a_end


def last_n_days(today, n):
    """The n dates ending with today, oldest first (today included)."""
    return [today - timedelta(days=i) for i in range(n - 1, -1, -1)]
