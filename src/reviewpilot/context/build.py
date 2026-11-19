import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from reviewpilot.context.budget import MAX_FILE_TOKENS, MAX_PR_TOKENS, est_tokens
from reviewpilot.context.diff import FileDiff, parse_patch
from reviewpilot.context.skip import MAX_FILES, skip_reason
from reviewpilot.context.symbols import Snippet, snippets_for


@dataclass
class FileContext:
    path: str
    status: str
    previous_path: str | None
    patch: str
    diff: FileDiff  # which new-file lines may receive comments
    snippets: list[Snippet]
    tokens: int


@dataclass
class PRContext:
    number: int
    title: str  # untrusted PR text; Phase 3 prompts must treat it as data
    head_sha: str
    files: list[FileContext] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(f.tokens for f in self.files)


def build_context(
    pr: dict,
    files: list[dict],
    get_content: Callable[[str], str | None],
    max_file_tokens: int = MAX_FILE_TOKENS,
    max_pr_tokens: int = MAX_PR_TOKENS,
) -> PRContext:
    ctx = PRContext(pr["number"], pr["title"], pr["head"]["sha"])
    for i, f in enumerate(files):
        path = f["filename"]
        reason = "too many files in PR" if i >= MAX_FILES else skip_reason(f)
        if reason:
            ctx.skipped.append((path, reason))
            continue
        diff = parse_patch(f["patch"])
        source = get_content(path)
        snippets = snippets_for(path, source, diff.added) if source else []
        tokens = est_tokens(f["patch"]) + sum(est_tokens(s.text) for s in snippets)
        while tokens > max_file_tokens and snippets:  # drop the biggest snippet first
            big = max(snippets, key=lambda s: len(s.text))
            snippets.remove(big)
            tokens -= est_tokens(big.text)
        if tokens > max_file_tokens:
            ctx.skipped.append((path, "patch exceeds file token budget"))
        elif ctx.tokens + tokens > max_pr_tokens:
            ctx.skipped.append((path, "PR token budget reached"))
        else:
            ctx.files.append(
                FileContext(
                    path,
                    f["status"],
                    f.get("previous_filename"),
                    f["patch"],
                    diff,
                    snippets,
                    tokens,
                )
            )
    return ctx


def main(argv: list[str]) -> None:
    """Live check: python -m reviewpilot.context.build owner/repo 12"""
    from reviewpilot.github.auth import installation_client
    from reviewpilot.github.pr import fetch_pr

    full_name, number = argv[0], int(argv[1])
    owner, repo = full_name.split("/")
    pr, files, get_content = fetch_pr(installation_client(owner, repo), full_name, number)
    ctx = build_context(pr, files, get_content)
    print(f"PR #{ctx.number} head={ctx.head_sha[:7]} files={len(ctx.files)} tokens~{ctx.tokens}")
    for f in ctx.files:
        names = ", ".join(f"{s.name}[{s.start}-{s.end}]" for s in f.snippets) or "-"
        print(f"  {f.status:9} {f.path}  tokens~{f.tokens}  commentable={sorted(f.diff.added)}")
        print(f"            symbols: {names}")
    for path, reason in ctx.skipped:
        print(f"  skipped   {path}: {reason}")


if __name__ == "__main__":
    main(sys.argv[1:])
