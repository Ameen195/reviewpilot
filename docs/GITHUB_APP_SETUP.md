# GitHub App setup (Phase 1)

1. Create a **public** test repo (e.g. `reviewpilot-test`) with a README.
2. Go to https://smee.io -> **Start a new channel** -> copy the channel URL.
3. GitHub -> Settings -> Developer settings -> GitHub Apps -> **New GitHub App**:
   - Name: unique, e.g. `reviewpilot-<yourname>`
   - Homepage URL: your repo URL
   - Webhook: Active; URL = the smee channel URL; Secret = a long random string
   - Permissions (Repository): Pull requests = Read & write, Contents = Read-only, Metadata = Read-only
   - Subscribe to events: **Pull request**
   - Where can it be installed: Only on this account
4. Create the app, then **Generate a private key** (.pem). Keep it outside git. Never share it.
5. Install the app on the test repo only.
6. Copy `.env.example` to `.env`, set `GITHUB_WEBHOOK_SECRET` to the same secret.

## Run locally (two terminals, folder `D:\Projects\reviewpilot`)

```powershell
uv run uvicorn reviewpilot.api.app:app --port 8000
```
```powershell
npx smee-client --url <your-smee-url> --target http://localhost:8000/webhook
```

Open a PR on the test repo: the server log shows `pull_request opened repo=... pr=#... head=...`.
