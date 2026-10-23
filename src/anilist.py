"""Metadata anime dari AniList GraphQL API (https://graphql.anilist.co).

Hanya metadata — tanpa kunci API (endpoint publik AniList).
Semua permintaan berbatas waktu + coba-ulang saat kena 429.
"""
import json
import time
import urllib.request
import urllib.error

API_URL = "https://graphql.anilist.co"
USER_AGENT = "screaperv1/1.0 (metadata scraper)"
TIMEOUT = 30

QUERY = """
query ($search: String, $id: Int) {
  Media(search: $search, id: $id, type: ANIME) {
    id
    idMal
    title { romaji english native }
    synonyms
    format
    status
    description(asHtml: false)
    episodes
    duration
    season
    seasonYear
    averageScore
    meanScore
    popularity
    genres
    source
    studios(isMain: true) { nodes { name } }
    coverImage { extraLarge large color }
    bannerImage
    trailer { id site }
    startDate { year month day }
    endDate { year month day }
  }
}
"""


def _post(payload, retries=3):
    data = json.dumps(payload).encode("utf-8")
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(API_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", USER_AGENT)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", "5"))
                time.sleep(min(wait, 60))
                continue
            if e.code in (500, 502, 503):
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"AniList tidak menjawab sesudah {retries} percobaan: {last_err}")


def _normalize(media):
    if not media:
        return None
    trailer = None
    tr = media.get("trailer")
    if tr and tr.get("site") == "youtube" and tr.get("id"):
        trailer = f"https://www.youtube.com/watch?v={tr['id']}"
    studios = [n["name"] for n in (media.get("studios") or {}).get("nodes", [])]
    cover = media.get("coverImage") or {}
    return {
        "anilistId": media.get("id"),
        "malId": media.get("idMal"),
        "title": media.get("title") or {},
        "synonyms": media.get("synonyms") or [],
        "format": media.get("format"),
        "status": media.get("status"),
        "synopsis": media.get("description"),
        "episodesTotal": media.get("episodes"),
        "durationMin": media.get("duration"),
        "season": media.get("season"),
        "year": media.get("seasonYear"),
        "score": media.get("averageScore"),
        "popularity": media.get("popularity"),
        "genres": media.get("genres") or [],
        "source": media.get("source"),
        "studios": studios,
        "poster": cover.get("extraLarge") or cover.get("large"),
        "posterColor": cover.get("color"),
        "banner": media.get("bannerImage"),
        "trailer": trailer,
        "startDate": media.get("startDate"),
        "endDate": media.get("endDate"),
    }


def fetch_by_title(title):
    """Cari satu anime berdasarkan judul (hasil teratas AniList)."""
    body = _post({"query": QUERY, "variables": {"search": title}})
    return _normalize((body.get("data") or {}).get("Media"))


def fetch_by_id(anilist_id):
    """Ambil satu anime berdasarkan ID AniList."""
    body = _post({"query": QUERY, "variables": {"id": int(anilist_id)}})
    return _normalize((body.get("data") or {}).get("Media"))
