from dataclasses import dataclass

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

_PARSER = Parser(Language(tspython.language()))
_DEFS = {"function_definition", "class_definition"}


@dataclass(frozen=True)
class Snippet:
    name: str
    start: int  # 1-based, inclusive
    end: int
    text: str


def _enclosing(root, line: int):
    node = root.descendant_for_point_range((line - 1, 0), (line - 1, 0))
    while node is not None and node.type not in _DEFS:
        node = node.parent
    if node is not None and node.parent is not None and node.parent.type == "decorated_definition":
        node = node.parent
    return node


def _windows(lines: set[int], total: int, window: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for n in sorted(lines):
        lo, hi = max(1, n - window), min(total, n + window)
        if spans and lo <= spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], max(spans[-1][1], hi))
        else:
            spans.append((lo, hi))
    return spans


def snippets_for(path: str, source: str, changed: set[int], window: int = 8) -> list[Snippet]:
    """Enclosing function/class of each changed line (Python); +-window lines otherwise."""
    src_lines = source.splitlines()
    found: dict[tuple[int, int], Snippet] = {}
    loose = set(changed)
    if path.endswith(".py"):
        root = _PARSER.parse(source.encode()).root_node
        loose = set()
        for n in changed:
            node = _enclosing(root, n)
            if node is None:
                loose.add(n)
                continue
            start, end = node.start_point[0] + 1, node.end_point[0] + 1
            inner = node.child_by_field_name("definition") or node
            name = inner.child_by_field_name("name").text.decode()
            found[(start, end)] = Snippet(name, start, end, "\n".join(src_lines[start - 1 : end]))
    loose = {
        n for n in loose if n <= len(src_lines) and src_lines[n - 1].strip()
    }  # blanks add nothing
    for lo, hi in _windows(loose, len(src_lines), window):
        if any(a <= lo and hi <= b for a, b in found):  # already inside an included symbol
            continue
        found[(lo, hi)] = Snippet("<lines>", lo, hi, "\n".join(src_lines[lo - 1 : hi]))
    return sorted(found.values(), key=lambda s: s.start)
