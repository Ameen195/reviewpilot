import json
from pathlib import Path

from reviewpilot.context.build import build_context
from reviewpilot.context.diff import parse_patch
from reviewpilot.context.symbols import snippets_for

FX = json.loads((Path(__file__).parent / "fixtures" / "pr_mixed.json").read_text())
FILES = {f["filename"]: f for f in FX["files"]}


def ctx(**kw):
    return build_context(FX["pr"], FX["files"], FX["contents"].get, **kw)


def test_multi_hunk_added_lines_and_hunk_ranges():
    d = parse_patch(FILES["app/calc.py"]["patch"])
    assert [(h.new_start, h.new_end) for h in d.hunks] == [(2, 9), (18, 21)]
    assert d.added == {5, 6, 21}


def test_can_comment_rules():
    d = parse_patch(FILES["app/calc.py"]["patch"])
    assert d.can_comment(6) and d.can_comment(6, start_line=5)
    assert not d.can_comment(4)  # context line, not changed
    assert not d.can_comment(10)  # outside every hunk
    assert not d.can_comment(21, start_line=6)  # range crosses hunks


def test_new_file_every_line_added():
    d = parse_patch(FILES["app/new_mod.py"]["patch"])
    assert d.added == {1, 2, 3}


def test_deletion_only_hunk_has_no_commentable_lines():
    d = parse_patch(FILES["app/old.py"]["patch"])
    assert d.added == set() and not d.can_comment(1)


def test_pure_deletion_hunk_inside_file():
    d = parse_patch("@@ -3,2 +2,0 @@\n-a\n-b")
    assert d.added == set() and d.hunks[0].new_end == 2


def test_no_newline_marker_ignored():
    d = parse_patch("@@ -1 +1 @@\n-a\n\\ No newline\n+b\n\\ No newline")
    assert d.added == {1}


def test_symbols_enclosing_function_and_method():
    src = FX["contents"]["app/calc.py"]
    snips = snippets_for("app/calc.py", src, {5, 6, 21})
    assert [(s.name, s.start, s.end) for s in snips] == [("add", 4, 6), ("spread", 20, 21)]
    assert "def add" in snips[0].text


def test_symbols_module_level_falls_back_to_window():
    snips = snippets_for("app/new_mod.py", FX["contents"]["app/new_mod.py"], {3})
    assert [s.name for s in snips] == ["<lines>"]


def test_symbols_non_python_uses_window():
    s = snippets_for("a.js", "\n".join(f"l{i}" for i in range(1, 40)), {20}, window=2)
    assert (s[0].start, s[0].end) == (18, 22)


def test_skip_rules_and_rename():
    c = ctx()
    assert [f.path for f in c.files] == ["app/calc.py", "app/util.py", "app/new_mod.py"]
    assert dict(c.skipped) == {
        "docs/b.md": "no diff text (rename only, binary or too large)",
        "app/old.py": "deleted file",
        "poetry.lock": "lock file",
        "logo.png": "binary file",
        "static/app.min.js": "generated or vendored file",
    }
    renamed = c.files[1]
    assert renamed.previous_path == "app/helpers.py" and renamed.diff.added == {2}


def test_token_budget_drops_snippets_then_files():
    full = ctx().files[0]
    calc = ctx(max_file_tokens=full.tokens - 1).files[0]  # patch still fits, a snippet is dropped
    assert calc.path == "app/calc.py" and len(calc.snippets) < len(full.snippets)
    tiny = ctx(max_file_tokens=5)
    assert not tiny.files and ("app/calc.py", "patch exceeds file token budget") in tiny.skipped
    capped = ctx(max_pr_tokens=ctx().files[0].tokens)
    assert [f.path for f in capped.files] == ["app/calc.py"]
    assert ("app/util.py", "PR token budget reached") in capped.skipped


def test_blank_line_outside_symbol_adds_no_window():
    src = "\n\ndef f():\n    return 1\n"
    snips = snippets_for("a.py", src, {1, 4})
    assert [(s.name, s.start, s.end) for s in snips] == [("f", 3, 4)]
