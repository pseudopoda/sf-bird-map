"""Reads eBird alert emails from Gmail, looks up each sighting, finds a photo,
and updates docs/sightings.json for the map."""
import os, re, json, base64, hashlib, random, html, datetime as dt
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

EBIRD_KEY = os.environ["EBIRD_API_KEY"]
REGION = "US-CA-075"  # San Francisco County
SENDER = os.environ.get("ALERT_SENDER", "ebird-alert@birds.cornell.edu")
LOOKBACK = os.environ.get("EMAIL_LOOKBACK", "2d")
DATA_FILE = "docs/sightings.json"
SPECIES_FILE = "docs/species.json"
HEADERS = {"X-eBirdApiToken": EBIRD_KEY}


# ---------- Gmail ----------
def gmail_service():
    creds = Credentials(
        None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def walk_parts(payload):
    yield payload
    for p in payload.get("parts", []) or []:
        yield from walk_parts(p)


def email_text(msg):
    plain, htm = "", ""
    for part in walk_parts(msg["payload"]):
        data = part.get("body", {}).get("data")
        if not data:
            continue
        raw = base64.urlsafe_b64decode(data).decode("utf-8", "replace")
        if part["mimeType"] == "text/plain":
            plain += raw
        elif part["mimeType"] == "text/html":
            htm += raw
    if htm:  # keep link targets, drop other tags
        htm = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>', r" \1 ", htm)
        htm = html.unescape(re.sub(r"<[^>]+>", " ", htm))
    return plain + "\n" + htm


def get_alert_emails(svc):
    res = svc.users().messages().list(
        userId="me", q=f"from:{SENDER} newer_than:{LOOKBACK}", maxResults=50
    ).execute()
    emails = []
    for m in res.get("messages", []):
        msg = svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
        subject = next(
            (h["value"] for h in msg["payload"]["headers"] if h["name"].lower() == "subject"), ""
        )
        emails.append({"subject": subject, "text": email_text(msg)})
    return emails


def alert_type(subject):
    s = subject.lower()
    if "need" in s:
        return "needs"
    if "rare" in s:
        return "rare"
    return "other"


# ---------- eBird API ----------
def ebird(path, **params):
    r = requests.get(f"https://api.ebird.org/v2/{path}", headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def load_region_obs():
    params = dict(back=14, detail="full", maxResults=10000)
    by_sub = {}
    for o in ebird(f"data/obs/{REGION}/recent", **params):
        by_sub.setdefault(o["subId"], []).append(o)
    notable = ebird(f"data/obs/{REGION}/recent/notable", **params)
    notable_by_sub = {}
    for o in notable:
        notable_by_sub.setdefault(o["subId"], []).append(o)
        by_sub.setdefault(o["subId"], [])
        if not any(x["speciesCode"] == o["speciesCode"] for x in by_sub[o["subId"]]):
            by_sub[o["subId"]].append(o)
    return by_sub, notable_by_sub


# ---------- Photos (Macaulay Library; unofficial endpoint, may change) ----------
ML_SEARCH = "https://search.macaulaylibrary.org/api/v1/search"


def ml_lookup(params):
    try:
        r = requests.get(
            ML_SEARCH,
            params={**params, "mediaType": "photo", "sort": "rating_rank_desc", "count": 1},
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("results", {}).get("content", [])
        return items[0] if items else None
    except Exception as e:
        print("  photo lookup failed:", e)
        return None


def find_photo(sub_id, code):
    asset, generic = ml_lookup({"subId": sub_id, "taxonCode": code}), False
    if not asset:
        asset, generic = ml_lookup({"taxonCode": code}), True
    if not asset:
        return None
    aid = asset["assetId"]
    return {
        "url": f"https://cdn.download.ams.birds.cornell.edu/api/v1/asset/{aid}/640",
        "page": f"https://macaulaylibrary.org/asset/{aid}",
        "credit": asset.get("userDisplayName", "Unknown"),
        "generic": generic,
    }


# ---------- Main ----------

def update_species_list():
    """Saves every species ever reported in San Francisco County (for the map's species picker)."""
    codes = ebird(f"product/spplist/{REGION}")
    tax = ebird("ref/taxonomy/ebird", fmt="json", cat="species", species=",".join(codes))
    tax.sort(key=lambda t: t.get("taxonOrder", 0))
    species = [{"code": t["speciesCode"], "name": t["comName"], "sci": t["sciName"]} for t in tax]
    with open(SPECIES_FILE, "w") as f:
        json.dump(species, f)
    print("species list:", len(species))

def jitter(sub_id, lat, lng):
    rnd = random.Random(hashlib.md5(sub_id.encode()).hexdigest())  # stable per checklist
    return lat + rnd.uniform(-0.003, 0.003), lng + rnd.uniform(-0.003, 0.003)


def main():
    try:
        update_species_list()
    except Exception as e:
        print('species list update failed:', e)
    try:
        with open(DATA_FILE) as f:
            store = {s["id"]: s for s in json.load(f)["sightings"]}
    except FileNotFoundError:
        store = {}

    by_sub, notable_by_sub = load_region_obs()
    emails = get_alert_emails(gmail_service())
    print(f"{len(emails)} alert emails, {len(by_sub)} checklists in region feed")

    for em in emails:
        kind = alert_type(em["subject"])
        text = em["text"]
        lowered = text.lower()
        for m in re.finditer(r"checklist/(S\d+)", text):
            sub = m.group(1)
            window = lowered[max(0, m.start() - 600): m.end() + 100]
            obs = [o for o in by_sub.get(sub, []) if o["comName"].lower() in window]
            if not obs:
                obs = notable_by_sub.get(sub, [])
            if not obs:
                print(f"  skipping {sub}: not found in San Francisco feed")
                continue
            for o in obs:
                key = f"{sub}:{o['speciesCode']}"
                if key in store:
                    if kind not in store[key]["alerts"]:
                        store[key]["alerts"].append(kind)
                    continue
                lat, lng, approx = o["lat"], o["lng"], False
                if o.get("locationPrivate"):
                    lat, lng = jitter(sub, lat, lng)
                    approx = True
                print("  adding", key, o["comName"])
                store[key] = {
                    "id": key,
                    "checklist": sub,
                    "species": o["comName"],
                    "sci": o.get("sciName"),
                    "code": o["speciesCode"],
                    "count": o.get("howMany"),
                    "location": o["locName"],
                    "lat": lat,
                    "lng": lng,
                    "approximate": approx,
                    "datetime": o["obsDt"],
                    "observer": o.get("userDisplayName"),
                    "alerts": [kind],
                    "photo": find_photo(sub, o["speciesCode"]),
                }

    out = {
        "generated": dt.datetime.utcnow().isoformat() + "Z",
        "sightings": sorted(store.values(), key=lambda s: s["datetime"], reverse=True),
    }
    with open(DATA_FILE, "w") as f:
        json.dump(out, f, indent=1)
    print("saved", len(out["sightings"]), "sightings")


if __name__ == "__main__":
    main()
