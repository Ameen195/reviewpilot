def mean(xs):
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def median(xs):
    """Middle value; for an even count, the mean of the two middle values."""
    if not xs:
        raise ValueError("median of empty list")
    s = sorted(xs)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def moving_average(xs, window):
    if window <= 0:
        raise ValueError("window must be positive")
    out = []
    for i in range(len(xs) - window + 1):
        out.append(sum(xs[i : i + window]) / window)
    return out


def top_n(xs, n):
    return sorted(xs, reverse=True)[:n]


def clamp(x, lo, hi):
    """Limit x to the range [lo, hi]."""
    return max(lo, min(x, hi))
