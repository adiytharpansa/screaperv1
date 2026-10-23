"""Pencarian torrent di Nyaa.si lewat RSS resmi (https://nyaa.si/?page=rss).

Kategori baku: 1_2 = Anime - English-translated.
Hasil RSS memuat seeders/leechers/downloads/ukuran/infoHash,
cukup untuk menyusun magnet link tanpa membuka halaman HTML.
"""
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

BASE = "https://nyaa.si/"
USER_AGENT = "Mozilla/5.0 (screaperv1; +https://github.com/adiytharpansa/screaperv1)"
TIMEOUT = 30
NS = {"nyaa": "https://nyaa.si/xmlns/nyaa"}

# Tracker publik yang sama seperti magnet bawaan Nyaa.
TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.bittor.pw:1337/announce",
    "udp://public.popcorn-tracker.org:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://exodus.desync.com:6969",
    "udp://open.demonii.com:1337/announce",
]


def build_magnet(info_hash, display_name):
    if not info_hash:
        return None
    parts = [f"magnet:?xt=urn:btih:{info_hash}"]
    if display_name:
        parts.append("dn=" + urllib.parse.quote(display_name))
    for tr in TRACKERS:
        parts.append("tr=" + urllib.parse.quote(tr, safe=""))
    return "&".join(parts)


def _text(item, tag, default=None):
    el = item.find(tag, NS) if tag.startswith("nyaa:") else item.find(tag)
    if el is None or el.text is None:
        return default
    return el.text.strip()


def _int(item, tag, default=0):
    raw = _text(item, tag)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def search(query, category="1_2", trusted_only=False, retries=3):
    """Satu pencarian RSS. Mengembalikan list dict rilis mentah."""
    params = {
        "page": "rss",
        "q": query,
        "c": category,
        "f": "2" if trusted_only else "0",
        "s": "seeders",
        "o": "desc",
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
            break
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"Nyaa tidak menjawab untuk {query!r}: {last_err}")

    root = ET.fromstring(raw)
    results = []
    for item in root.iter("item"):
        title = _text(item, "title", "")
        info_hash = _text(item, "nyaa:infoHash")
        results.append({
            "rawTitle": title,
            "torrentUrl": _text(item, "link"),
            "pageUrl": _text(item, "guid"),
            "pubDate": _text(item, "pubDate"),
            "seeders": _int(item, "nyaa:seeders"),
            "leechers": _int(item, "nyaa:leechers"),
            "downloads": _int(item, "nyaa:downloads"),
            "size": _text(item, "nyaa:size"),
            "infoHash": info_hash,
            "category": _text(item, "nyaa:category"),
            "trusted": _text(item, "nyaa:trusted") == "Yes",
            "remake": _text(item, "nyaa:remake") == "Yes",
            "magnet": build_magnet(info_hash, title),
        })
    return results


def search_title(names, **kwargs):
    """Cari memakai beberapa varian nama (romaji/inggris), gabung + dedupe infoHash."""
    merged = {}
    for name in names:
        if not name:
            continue
        for rel in search(name, **kwargs):
            key = rel.get("infoHash") or rel.get("pageUrl")
            if key and key not in merged:
                merged[key] = rel
        time.sleep(1)  # sopan ke Nyaa di antara varian nama
    return list(merged.values())
