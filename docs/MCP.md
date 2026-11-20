# MCP server

Lets Claude Desktop (or any MCP client) inspect PRs through ReviewPilot. It runs locally over stdio.

## Tools (all read-only; nothing is ever posted to GitHub)

| Tool | What it does | Cost / needs |
|------|--------------|--------------|
| `get_pr_context(repo, number)` | Changed files, diffs, skipped files and why | GitHub App |
| `review_file(repo, number, path)` | Runs the three reviewers on one changed file | **Uses Groq tokens** (counts against the daily limit); no tests run |
| `run_tests_sandboxed(repo, number)` | Runs the PR head's tests in the locked-down Docker sandbox | Docker + sandbox image, see `SANDBOX.md` |
| `list_findings(repo, number)` | Findings from the stored review of the PR's current head commit | Free; reads `data/checkpoints.sqlite`, never calls the LLM |

`list_findings` finds a review by the same key the worker uses (`owner/repo#number@head_sha`), so it only
sees PRs the queue worker has already reviewed. `posted: false` means the review is still paused for approval.

## Safety

- Only repos where the GitHub App is installed work; anything else returns an error.
- Optional `ALLOWED_REPOS=owner/a,owner/b` in `.env` narrows that further.
- Secrets stay in `.env` in the project folder (loaded by the server's settings). The Claude Desktop
  config holds only the command and directory.
- stdout is the protocol channel; all logs go to stderr (a test enforces this).

## Connect to Claude Code (tested)

Run once, from any folder (`--directory` makes `uv` use the project, so `.env` is found):

```
claude mcp add reviewpilot -- uv run --directory D:\Projects\reviewpilot python -m reviewpilot.mcp_server
```

Then check with `claude mcp list` (reviewpilot should be connected) or `/mcp` inside Claude Code, and ask:
"Use reviewpilot's get_pr_context on owner/repo PR 1."

## Connect to Claude Desktop (Windows, optional, not tested)

1. Make sure `.env` has `GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY_PATH`, `GROQ_API_KEY`.
2. Open Claude Desktop > Settings > Developer > Edit Config (`%APPDATA%\Claude\claude_desktop_config.json`).
3. Add:

```json
{
  "mcpServers": {
    "reviewpilot": {
      "command": "uv",
      "args": ["run", "--directory", "D:\Projects\reviewpilot", "python", "-m", "reviewpilot.mcp_server"]
    }
  }
}
```

4. Quit Claude Desktop fully (tray icon > Quit) and reopen it. The tools appear under the connectors/tools menu.
5. Try: "Use reviewpilot get_pr_context on owner/repo PR 1."

If `uv` is not found, put its full path in `command`. Logs: `%APPDATA%\Claude\logs\mcp-server-reviewpilot.log`.
