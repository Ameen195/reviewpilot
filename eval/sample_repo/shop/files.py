import csv
import os


def read_lines(path):
    with open(path, encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f]


def write_report(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "total"])
        writer.writerows(rows)


def file_size(path):
    return os.path.getsize(path)


def safe_join(base, name):
    full = os.path.realpath(os.path.join(base, name))
    if not full.startswith(os.path.realpath(base) + os.sep):
        raise ValueError("path escapes base directory")
    return full
