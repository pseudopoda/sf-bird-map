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

## Photos, nearby counties and schedule
- The script runs every 3 hours (edit the `cron` line in `.github/workflows/update.yml` to change it; `0 16 * * *` means once a day).
- Rare birds also come straight from eBird for SF plus Alameda, Contra Costa, Marin, San Mateo and Santa Clara counties. They don't need an email. Your "needs" still come from your alert emails and stay SF only.
- Photos are downloaded once into `docs/photos/` and reused, so the map never depends on live image links. If no photo is found for an observation, it falls back to a generic species photo (Macaulay Library, then iNaturalist).
- Markers fade from dark (today) to light (6 days ago). Only the last 7 days are kept.
- If photos are still missing, open the Actions log of a run and look for lines containing "Macaulay search" or "image download failed", and send them to Claude.

## Refresh now button (one-time token per device)
The map's **Refresh now** button asks GitHub to run the update immediately, then reloads the data when it's done (usually 1-3 minutes).
1. On GitHub: your profile picture > **Settings** > **Developer settings** > **Personal access tokens** > **Fine-grained tokens** > **Generate new token**.
2. Name it "bird map refresh", pick an expiration (up to 1 year), and under **Repository access** choose **Only select repositories** > your `sf-bird-map` repo.
3. Under **Permissions > Repository permissions**, set **Actions** to **Read and write**. Leave everything else alone. Generate and copy the token (you only see it once).
4. Open the map on your device, tap **Refresh now**, and paste the token when asked. It's stored only in that browser. Never put it in the repo.
Each place you use the map (Safari, the home-screen app, your PC) keeps its own copy, so paste it once in each. If it expires or you revoke it, the button will ask for a new one.

## Add to Home Screen
- iPhone/iPad: open the map in Safari > Share button > **Add to Home Screen**.
- Windows (Chrome or Edge): the install icon in the address bar, or menu > **Install**.
The home-screen version keeps its own starred list, hidden list and token separate from Safari.
