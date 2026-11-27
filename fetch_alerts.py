"""Builds the data for the SF bird map.

Sources:
  * Your eBird alert emails (Gmail)  -> tells us which sightings are "needs" for you
  * eBird API "notable" feeds        -> rare birds in SF County and nearby Bay Area counties
Photos are downloaded once and stored in docs/photos/ so the map never depends on live hotlinks.
"""
import os, re, json, base64, hashlib, random, html, time, pathlib, datetime as dt
from zoneinfo import ZoneInfo
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

EBIRD_KEY = os.environ["EBIRD_API_KEY"]
HOME_REGION, HOME_NAME = "US-CA-075", "San Francisco"
NEARBY = {  # rare/notable birds only
    "US-CA-001": "Alameda",       # Oakland, Berkeley
    "US-CA-013": "Contra Costa",
    "US-CA-041": "Marin",
    "US-CA-081": "San Mateo",
    "US-CA-085": "Santa Clara",   # San Jose
}
KEEP_DAYS = 7
SENDER = os.environ.get("ALERT_SENDER", "ebird-alert@birds.cornell.edu")
LOOKBACK = os.environ.get("EMAIL_LOOKBACK", "2d")
DATA_FILE = "docs/sightings.json"
SPECIES_FILE = "docs/species.json"
PHOTO_INDEX = "docs/photos.json"
ARCHIVE_DIR = pathlib.Path("docs/archive")
PHOTO_DIR = pathlib.Path("docs/photos")
HEADERS = {"X-eBirdApiToken": EBIRD_KEY}
UA = {"User-Agent": "sf-bird-map/1.0 (personal project)"}
TODAY = dt.datetime.now(ZoneInfo("America/Los_Angeles")).date()


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
    if htm:
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


def update_species_list():
    codes = ebird(f"product/spplist/{HOME_REGION}")
    tax = ebird("ref/taxonomy/ebird", fmt="json", cat="species", species=",".join(codes))
    tax.sort(key=lambda t: t.get("taxonOrder", 0))
    species = [{"code": t["speciesCode"], "name": t["comName"], "sci": t["sciName"]} for t in tax]
    with open(SPECIES_FILE, "w") as f:
        json.dump(species, f)
    print("species list:", len(species))


def region_obs(region):
    """Returns (all recent obs grouped by checklist, notable obs grouped by checklist)."""
    params = dict(back=KEEP_DAYS, detail="full", maxResults=10000)
    by_sub, notable_by_sub = {}, {}
    for o in ebird(f"data/obs/{region}/recent", **params):
        by_sub.setdefault(o["subId"], []).append(o)
    for o in ebird(f"data/obs/{region}/recent/notable", **params):
        notable_by_sub.setdefault(o["subId"], []).append(o)
        lst = by_sub.setdefault(o["subId"], [])
        if not any(x["speciesCode"] == o["speciesCode"] for x in lst):
            lst.append(o)
    return by_sub, notable_by_sub


# ---------- Photos: downloaded once, stored in docs/photos/ ----------
def save_image(url, name):
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if not ctype.startswith("image"):
            raise ValueError(f"not an image ({ctype})")
        ext = {"image/png": "png", "image/webp": "webp"}.get(ctype.split(";")[0], "jpg")
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        (PHOTO_DIR / f"{name}.{ext}").write_bytes(r.content)
        return f"photos/{name}.{ext}"
    except Exception as e:
        print(f"  image download failed ({url}): {e}")
        return None


def ml_lookup(params):
    """Macaulay Library search (unofficial endpoint, so we log what happens)."""
    try:
        r = requests.get(
            "https://search.macaulaylibrary.org/api/v1/search",
            params={**params, "mediaType": "photo", "sort": "rating_rank_desc", "count": 1},
            headers=UA, timeout=20,
        )
        if r.status_code != 200:
            print(f"  Macaulay search HTTP {r.status_code} for {params}: {r.text[:150]!r}")
            return None
        items = r.json().get("results", {}).get("content", [])
        if not items:
            print(f"  Macaulay search: no results for {params}")
        return items[0] if items else None
    except Exception as e:
        print("  Macaulay search failed:", e)
        return None


def ml_entry(asset, generic, name):
    aid = asset["assetId"]
    f = save_image(f"https://cdn.download.ams.birds.cornell.edu/api/v1/asset/{aid}/640", name)
    if not f:
        return None
    return {"file": f, "page": f"https://macaulaylibrary.org/asset/{aid}",
            "credit": asset.get("userDisplayName") or "Unknown",
            "generic": generic, "source": "Macaulay Library"}


def inat_entry(sci, name):
    """Reliable open-licensed fallback: iNaturalist's default photo for the species."""
    try:
        r = requests.get("https://api.inaturalist.org/v1/taxa",
                         params={"q": sci, "rank": "species", "per_page": 5}, headers=UA, timeout=20)
        r.raise_for_status()
        for t in r.json().get("results", []):
            p = t.get("default_photo")
            if p and t.get("name", "").lower() == (sci or "").lower():
                url = p.get("medium_url") or p.get("url", "").replace("square", "medium")
                f = save_image(url, name)
                if f:
                    return {"file": f, "page": f"https://www.inaturalist.org/taxa/{t['id']}",
                            "credit": p.get("attribution") or "iNaturalist contributor",
                            "generic": True, "source": "iNaturalist"}
    except Exception as e:
        print("  iNaturalist lookup failed:", e)
    return None


def get_photo(sub, code, sci, index, observation_only=False):
    okey = f"obs:{sub}:{code}"
    if okey in index:
        return index[okey]
    asset = ml_lookup({"subId": sub, "taxonCode": code})
    time.sleep(0.3)
    if asset:
        e = ml_entry(asset, False, f"{sub}_{code}")
        if e:
            index[okey] = e
            return e
    if observation_only:
        return None
    gkey = f"species:{code}"
    if gkey in index:
        return index[gkey]
    asset = ml_lookup({"taxonCode": code})
    e = ml_entry(asset, True, f"species_{code}") if asset else None
    e = e or inat_entry(sci, f"species_{code}")
    if e:
        index[gkey] = e
    return e


# ---------- Main ----------
def jitter(sub_id, lat, lng):
    rnd = random.Random(hashlib.md5(sub_id.encode()).hexdigest())
    return lat + rnd.uniform(-0.003, 0.003), lng + rnd.uniform(-0.003, 0.003)


def obs_age_days(obs_dt):
    return (TODAY - dt.date.fromisoformat(obs_dt[:10])).days


def load_archive():
    recs = {}
    for p in sorted(ARCHIVE_DIR.glob("20*.json")):
        for r in json.loads(p.read_text()):
            recs[r["id"]] = r
    return recs


def save_archive(recs):
    """Every checklist-level sighting is kept forever, one file per month."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    months = {}
    for r in recs.values():
        months.setdefault(r["datetime"][:7], []).append(r)
    index = []
    for m, rows in sorted(months.items()):
        rows.sort(key=lambda r: (r["datetime"], r["id"]))
        (ARCHIVE_DIR / f"{m}.json").write_text("[\n" + ",\n".join(json.dumps(r) for r in rows) + "\n]")
        index.append({"month": m, "count": len(rows)})
    (ARCHIVE_DIR / "index.json").write_text(json.dumps(index))


def build_groups(recs):
    """One marker per bird per place, with staying / one-day-wonder status."""
    groups = {}
    for r in recs.values():
        if obs_age_days(r["datetime"]) <= 30:
            groups.setdefault((r["code"], r.get("locId") or r["location"]), []).append(r)
    out = []
    for rows in groups.values():
        rows.sort(key=lambda r: r["datetime"])
        latest = rows[-1]
        dates = sorted({r["datetime"][:10] for r in rows})
        age = (TODAY - dt.date.fromisoformat(dates[-1])).days
        if age > KEEP_DAYS:
            continue
        streak = 1
        for a, b in zip(dates[-2::-1], dates[::-1]):
            if (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days == 1:
                streak += 1
            else:
                break
        if age >= 2:
            status = "gone"
        elif age == 0:
            status = "staying" if len(dates) >= 2 else "new"
        else:
            status = "maybe"
        photo = next((r["photo"] for r in reversed(rows) if r.get("photo") and not r["photo"].get("generic")),
                     latest.get("photo"))
        item = dict(latest)
        item.update(photo=photo, dates=dates, days_reported=len(dates), streak=streak, status=status,
                    reports=len(rows), alerts=sorted({a for r in rows for a in r["alerts"]}),
                    confirmed=any(r.get("confirmed") for r in rows))
        out.append(item)
    return sorted(out, key=lambda s: s["datetime"], reverse=True)


def main():
    try:
        update_species_list()
    except Exception as e:
        print("species list update failed:", e)
    store = load_archive()
    try:
        index = json.load(open(PHOTO_INDEX))
    except FileNotFoundError:
        index = {}

    def add(o, kind, county):
        if obs_age_days(o["obsDt"]) > KEEP_DAYS:
            return
        key = f"{o['subId']}:{o['speciesCode']}"
        confirmed = bool(o.get("obsReviewed") and o.get("obsValid"))
        if key in store:
            if kind not in store[key]["alerts"]:
                store[key]["alerts"].append(kind)
            store[key]["confirmed"] = store[key].get("confirmed", False) or confirmed
            return
        lat, lng, approx = o["lat"], o["lng"], False
        if o.get("locationPrivate"):
            lat, lng = jitter(o["subId"], lat, lng)
            approx = True
        print("  adding", key, o["comName"], f"({county})")
        store[key] = {
            "id": key, "checklist": o["subId"], "species": o["comName"], "sci": o.get("sciName"),
            "code": o["speciesCode"], "count": o.get("howMany"), "location": o["locName"],
            "locId": o.get("locId"), "county": county, "lat": lat, "lng": lng, "approximate": approx,
            "datetime": o["obsDt"], "observer": o.get("userDisplayName"), "confirmed": confirmed,
            "alerts": [kind],
            "photo": get_photo(o["subId"], o["speciesCode"], o.get("sciName"), index),
        }

    # 1) Your alert emails (needs + rare) matched against SF County data
    by_sub, notable_by_sub = region_obs(HOME_REGION)
    emails = get_alert_emails(gmail_service())
    print(f"{len(emails)} alert emails, {len(by_sub)} checklists in SF feed")
    for em in emails:
        kind, text = alert_type(em["subject"]), em["text"]
        lowered = text.lower()
        for m in re.finditer(r"checklist/(S\d+)", text):
            sub = m.group(1)
            window = lowered[max(0, m.start() - 600): m.end() + 100]
            obs = [o for o in by_sub.get(sub, []) if o["comName"].lower() in window]
            obs = obs or notable_by_sub.get(sub, [])
            if not obs:
                print(f"  skipping {sub}: not found in San Francisco feed")
            for o in obs:
                add(o, kind, HOME_NAME)

    # 2) Rare birds straight from eBird: SF County + nearby counties (no email needed)
    for subs in notable_by_sub.values():
        for o in subs:
            add(o, "rare", HOME_NAME)
    for region, county in NEARBY.items():
        try:
            for o in ebird(f"data/obs/{region}/recent/notable", back=KEEP_DAYS, detail="full", maxResults=1000):
                add(o, "rare", county)
        except Exception as e:
            print(f"  nearby region {county} failed:", e)

    # 3) Retry photos for recent sightings that only have a generic photo (or none)
    for s in store.values():
        if obs_age_days(s["datetime"]) > 3:
            continue
        if s.get("photo") is None:
            s["photo"] = get_photo(s["checklist"], s["code"], s["sci"], index)
        elif s["photo"].get("generic"):
            s["photo"] = get_photo(s["checklist"], s["code"], s["sci"], index, observation_only=True) or s["photo"]

    save_archive(store)
    out = {"generated": dt.datetime.utcnow().isoformat() + "Z", "sightings": build_groups(store)}
    json.dump(out, open(DATA_FILE, "w"), indent=1)
    json.dump(index, open(PHOTO_INDEX, "w"), indent=1)
    print("map:", len(out["sightings"]), "birds;", "archive:", len(store), "records;", len(index), "photos cached")


if __name__ == "__main__":
    main()
