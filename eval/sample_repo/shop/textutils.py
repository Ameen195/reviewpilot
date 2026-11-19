import re


def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return text.strip("-")


def truncate(text, limit, suffix="..."):
    """Shorten text to at most `limit` characters, suffix included."""
    if len(text) <= limit:
        return text
    return text[: limit - len(suffix)] + suffix


def word_count(text):
    return len(text.split())


def chunk(items, size):
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[i : i + size] for i in range(0, len(items), size)]


def initials(name):
    return "".join(part[0].upper() for part in name.split() if part)
