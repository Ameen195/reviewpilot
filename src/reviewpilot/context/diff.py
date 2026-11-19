import re
from dataclasses import dataclass

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class Hunk:
    new_start: int
    new_end: int  # inclusive; new_start - 1 for a pure-deletion hunk
    added: frozenset[int]  # new-file line numbers of '+' lines


@dataclass(frozen=True)
class FileDiff:
    hunks: tuple[Hunk, ...]

    @property
    def added(self) -> set[int]:
        return {n for h in self.hunks for n in h.added}

    def can_comment(self, line: int, start_line: int | None = None) -> bool:
        """True if a RIGHT-side review comment on `line` (or start_line..line) is allowed.

        Rule: `line` must be an added line; start_line must be in the same hunk.
        """
        for h in self.hunks:
            if line in h.added:
                return start_line is None or h.new_start <= start_line < line
        return False


def parse_patch(patch: str) -> FileDiff:
    """Parse GitHub's per-file `patch` (hunks only, no ---/+++ headers)."""
    hunks: list[Hunk] = []
    new_line, start, added = 0, 0, set()
    in_hunk = False

    def close():
        if in_hunk:
            hunks.append(Hunk(start, new_line - 1, frozenset(added)))

    for raw in patch.split("\n"):
        m = _HUNK.match(raw)
        if m:
            close()
            start = new_line = int(m.group(1))
            if m.group(2) == "0":  # "+N,0": nothing on the new side; N is the line before
                start = new_line = new_line + 1
            added, in_hunk = set(), True
        elif not in_hunk or raw.startswith("\\"):
            continue
        elif raw.startswith("+"):
            added.add(new_line)
            new_line += 1
        elif raw.startswith("-"):
            continue
        elif raw != "":  # context line; "" is only the split artifact of a trailing newline
            new_line += 1
    close()
    return FileDiff(tuple(hunks))
