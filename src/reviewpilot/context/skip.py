import re

MAX_FILES = 100
MAX_PATCH_CHARS = 40_000

_LOCK = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
    "go.sum",
}
_GENERATED = re.compile(
    r"(\.min\.(js|css)$|\.map$|_pb2(_grpc)?\.py$|\.pb\.go$|(^|/)(dist|build|vendor|node_modules)/)"
)
_BINARY = re.compile(
    r"\.(png|jpe?g|gif|ico|webp|pdf|zip|gz|tar|jar|exe|dll|so|woff2?|ttf|mp[34]|sqlite)$",
    re.IGNORECASE,
)


def skip_reason(f: dict) -> str | None:
    """f is one item of GET /pulls/{n}/files. Returns why to skip it, or None."""
    path = f["filename"]
    if f["status"] == "removed":
        return "deleted file"
    if path.rsplit("/", 1)[-1] in _LOCK:
        return "lock file"
    if _GENERATED.search(path):
        return "generated or vendored file"
    if _BINARY.search(path):
        return "binary file"
    patch = f.get("patch")
    if not patch:  # GitHub omits patch for binary, rename-only and very large diffs
        return "no diff text (rename only, binary or too large)"
    if len(patch) > MAX_PATCH_CHARS:
        return "huge patch"
    return None
