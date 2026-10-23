# SF eBird Alerts Map: setup guide (about 30 minutes, one time)

You'll create four things: a GitHub repo, an eBird API key, Gmail read access, and secrets. After that it runs by itself every day.

## 1. Make the GitHub repo
1. Sign up at github.com (free) and click **New repository**. Name it `sf-bird-map`, set it to **Public** (needed for free GitHub Pages), and create it.
2. Click **uploading an existing file** and drag in everything from this folder (keep the `docs` folder and the `.github/workflows` folder structure; if the hidden `.github` folder is hard to upload, use **Add file > Create new file**, type `.github/workflows/update.yml` as the name, and paste the contents).
3. Go to **Settings > Pages**. Under "Build and deployment", pick **Deploy from a branch**, branch `main`, folder `/docs`. Save. Your map will live at `https://YOUR-USERNAME.github.io/sf-bird-map/`.

## 2. Get an eBird API key
Go to https://ebird.org/api/keygen (sign in), fill out the short form, copy the key.

## 3. Give the script read-only Gmail access
1. Go to https://console.cloud.google.com, create a project (any name).
2. **APIs & Services > Library**: search "Gmail API" and click **Enable**.
3. **APIs & Services > OAuth consent screen** (may be called Google Auth Platform): choose External, fill in app name and your email. Add yourself as a test user.
4. **IMPORTANT:** then click **Publish app** / set status to **In production**. If it stays in "Testing", Google expires the token after 7 days and the automation will quietly break. For personal use you don't need verification; you'll just see an "unverified app" warning once, which is fine because it's your own app.
5. **Credentials > Create credentials > OAuth client ID > Desktop app**. Download the JSON and save it as `client_secret.json`.
6. On your computer, install Python (python.org), then in a terminal in this folder run:
   ```
   pip install google-auth-oauthlib
   python get_token.py
   ```
   A browser opens; approve access. The terminal prints a CLIENT_ID, CLIENT_SECRET and REFRESH_TOKEN. Keep these private and do **not** upload `client_secret.json` to GitHub.

## 4. Add the secrets to GitHub
In your repo: **Settings > Secrets and variables > Actions > New repository secret**. Add four secrets with these exact names:
- `EBIRD_API_KEY`
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKEN`

## 5. Test it
**Actions** tab > "Update bird map" > **Run workflow**. Watch the log; when it's green, reload your map page. From then on it runs every morning on its own.

## Troubleshooting
- No emails found: check that the sender address in `fetch_alerts.py` matches the From address on your alerts (set a repo secret/env `ALERT_SENDER` if different).
- Sightings skipped: the log says why. Hidden/sensitive-species records may not be in the public API.
- No photos: the Macaulay Library search is unofficial and may change; the map still works without photos.

## Hiding species you don't care about
On the map, click **Species** to open the full San Francisco County list (refreshed daily). Uncheck any bird to hide it, or click **Hide this species** inside any popup. Your choices are saved in that browser, so your phone and PC each keep their own list. Hidden birds are only hidden from view, never deleted, so you can bring them back any time.
