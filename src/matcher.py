"""Penguraian judul rilis Nyaa + pemilihan rilis terbaik per episode.

Judul rilis umumnya berbentuk:
  [Group] Judul Anime - 12 [1080p][ABCDEF12].mkv
  [Group] Judul Anime - 01-28 (Batch) [1080p]
Rilis batch/rentang masuk keranjang `batches`, sisanya per episode.
"""
import re

RE_GROUP = re.compile(r"^\[([^\]]+)\]\s*")
RE_SEASON_WORD = re.compile(r"\b(\d)(?:st|nd|rd|th)\s+Season\b", re.IGNORECASE)
RE_SEASON_S = re.compile(r"\bS(\d)\b")
RE_SEASON_FULL = re.compile(r"\bSeason\s+(\d)\b", re.IGNORECASE)
RE_QUALITY = re.compile(r"\b(2160p|1080p|720p|480p|360p)\b", re.IGNORECASE)
RE_RANGE = re.compile(r"\b(\d{1,3})\s*[-~]\s*(\d{1,3})\b")
RE_BATCH_WORD = re.compile(r"\b(batch|complete|collection)\b", re.IGNORECASE)
RE_EP_DASH = re.compile(r"\s-\s(\d{1,4})(?:v\d+)?\b")
RE_EP_TAG = re.compile(r"\b(?:EP|E)\s?(\d{1,4})(?:v\d+)?\b", re.IGNORECASE)
RE_EP_BRACKET = re.compile(r"\[(\d{1,3})\]")

QUALITY_RANK = {"2160p": 4, "1080p": 3, "720p": 2, "480p": 1, "360p": 0}


def season_of(title):
    """Nomor musim dari penanda judul ('2nd Season', 'S2', 'Season 3'); None bila tak ada."""
    if not title:
        return None
    for pattern in (RE_SEASON_WORD, RE_SEASON_FULL, RE_SEASON_S):
        m = pattern.search(title)
        if m:
            return int(m.group(1))
    return None


_SEP_CHARS = " \t-_:—–.,'\"()[]"
_IGNORE_TOKENS = {"tv"}


def is_foreign_title(raw_title, names):
    """True bila judul rilis jelas milik entri LAIN (arc/lanjutan berjudul beda).

    Rilis satu entri umumnya persis 'Judul - 05'. Bila sesudah nama judul yang
    dikenal masih ada sisa kata (mis. ': Shimetsu Kaiyuu - Zenpen'), rilis itu
    milik entri arc/musim lain. Bila nama judul tidak dikenal sama sekali,
    tidak bisa dibuktikan asing -> False (dipertahankan).
    """
    if not names:
        return False
    title = RE_GROUP.sub("", raw_title or "").strip()
    low = title.lower()
    for name in sorted(names, key=len, reverse=True):
        if not name:
            continue
        n = name.lower().strip()
        if low.startswith(n):
            rest = low[len(n):]
            # Potong di penanda episode/ekor berkas, sisakan kepala judul saja.
            rest = re.split(r"\s-\s\d|\[\d{3,4}p|\.\w{3}$", rest)[0]
            rest = re.sub(r"\(\d{4}\)", " ", rest)
            words = [w for w in re.split(r"[^a-z]+", rest)
                     if len(w) >= 3 and w not in _IGNORE_TOKENS]
            return bool(words)
    return False


def parse_release(raw_title):
    title = raw_title or ""
    group = None
    m = RE_GROUP.match(title)
    if m:
        group = m.group(1)
    qm = RE_QUALITY.search(title)
    quality = qm.group(1).lower() if qm else None

    is_batch = bool(RE_BATCH_WORD.search(title))
    ep_range = None
    rm = RE_RANGE.search(title)
    if rm:
        a, b = int(rm.group(1)), int(rm.group(2))
        if 0 < a < b <= 500:
            ep_range = f"{a}-{b}"
            is_batch = True

    episode = None
    if not is_batch:
        for pattern in (RE_EP_DASH, RE_EP_TAG, RE_EP_BRACKET):
            em = pattern.search(title)
            if em:
                episode = int(em.group(1))
                break

    return {
        "group": group,
        "quality": quality,
        "episode": episode,
        "range": ep_range,
        "season": season_of(title),
        "isBatch": is_batch or episode is None,
    }


def _score(rel):
    """Skor pemilihan: seeders utama, kualitas penyeimbang."""
    q = QUALITY_RANK.get((rel.get("quality") or "").lower(), 0)
    trusted = 500 if rel.get("trusted") else 0
    return (rel.get("seeders", 0) + trusted, q)


def organize(releases, expected_season=None, names=None, max_episode=None):
    """Pisahkan rilis menjadi {episodes: [...terbaik per episode...], batches: [...]}.

    Setiap episode menyimpan SATU rilis terbaik; jumlah alternatif dicatat.
    Batch diurutkan dari seeders terbanyak.
    Buang: rilis berpenanda musim LAIN, rilis milik entri arc lain
    (is_foreign_title), dan episode di luar jumlah total entri ini
    (penomoran absolut waralaba, mis. ep 59 di entri 24 episode).
    """
    by_ep = {}
    alt_count = {}
    batches = []
    for rel in releases:
        if is_foreign_title(rel.get("rawTitle", ""), names):
            continue
        info = parse_release(rel.get("rawTitle", ""))
        if (expected_season is not None and info["season"] is not None
                and info["season"] != expected_season):
            continue
        if (max_episode is not None and info["episode"] is not None
                and info["episode"] > max_episode):
            continue
        entry = {**rel, **info}
        entry.pop("isBatch", None)
        if info["isBatch"]:
            batches.append(entry)
            continue
        ep = info["episode"]
        alt_count[ep] = alt_count.get(ep, 0) + 1
        current = by_ep.get(ep)
        if current is None or _score(entry) > _score(current):
            if current is not None:
                alt_count[ep] -= 0  # alternatif tetap dihitung dari total kandidat
            by_ep[ep] = entry
    episodes = []
    for ep in sorted(by_ep):
        entry = dict(by_ep[ep])
        entry["alternatives"] = max(alt_count.get(ep, 1) - 1, 0)
        episodes.append(entry)
    batches.sort(key=lambda r: r.get("seeders", 0), reverse=True)
    return {"episodes": episodes, "batches": batches[:10]}


def filter_episode(releases, episode, expected_season=None, names=None):
    """Saring rilis mentah menjadi kandidat SATU episode tertentu (bukan batch,
    bukan musim lain, bukan milik entri arc lain). Dipakai sapuan per-episode."""
    out = []
    for rel in releases:
        if is_foreign_title(rel.get("rawTitle", ""), names):
            continue
        info = parse_release(rel.get("rawTitle", ""))
        if info["isBatch"] or info["episode"] != episode:
            continue
        if (expected_season is not None and info["season"] is not None
                and info["season"] != expected_season):
            continue
        entry = {**rel, **info}
        entry.pop("isBatch", None)
        out.append(entry)
    return out


def best_of(candidates):
    """Rilis terbaik dari daftar kandidat (seeders + trusted + kualitas)."""
    if not candidates:
        return None
    return max(candidates, key=_score)
