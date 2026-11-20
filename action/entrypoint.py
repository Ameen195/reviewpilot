"""GitHub Action entrypoint: review the PR from the event payload, post one comment-only review.

Uses the workflow's GITHUB_TOKEN (REST) and the repo's GROQ_API_KEY secret. No queue, no human
approval pause (critical findings are posted with their severity), no Docker tests.
"""

import json
import os
import sys

from github import Auth, Github

from reviewpilot.agents.graph import review
from reviewpilot.agents.llm import chat_json
from reviewpilot.context.build import build_context
from reviewpilot.github.post import post_review
from reviewpilot.github.pr import fetch_pr


def run(gh: Github, repo: str, ctx, llm=chat_json) -> str:
    state = review(ctx, llm)
    return "posted" if post_review(gh, repo, ctx, state) else "already reviewed"


def main() -> int:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    pr, repo = event["pull_request"], event["repository"]["full_name"]
    head = pr["head"]["repo"]
    if head is None or head["full_name"] != repo:  # fork PR: read-only token, secrets withheld
        print("Fork PR: skipped (see README, Action mode).")
        return 0
    gh = Github(auth=Auth.Token(os.environ["GITHUB_TOKEN"]))
    ctx = build_context(*fetch_pr(gh, repo, pr["number"]))
    print(run(gh, repo, ctx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
