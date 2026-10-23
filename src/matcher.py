"""Penguraian judul rilis Nyaa + pemilihan rilis terbaik per episode.

Judul rilis umumnya berbentuk:
  [Group] Judul Anime - 12 [1080p][ABCDEF12].mkv
  [Group] Judul Anime - 01-28 (Batch) [1080p]
Rilis batch/rentang masuk keranjang `batches`, sisanya per episode.
"""
import re

RE_GROUP = re.compile(r"^\[([^\]]+)\]\s*")
RE_QUALITY = re.compile(r"\b(2160p|1080p|720p|480p|360p)\b", re.IGNORECASE)
RE_RANGE = re.compile(r"\b(\d{1,3})\s*[-~]\s*(\d{1,3})\b")
RE_BATCH_WORD = re.compile(r"\b(batch|complete|collection)\b", re.IGNORECASE)
RE_EP_DASH = re.compile(r"\s-\s(\d{1,4})(?:v\d+)?\b")
RE_EP_TAG = re.compile(r"\b(?:EP|E)\s?(\d{1,4})(?:v\d+)?\b", re.IGNORECASE)
RE_EP_BRACKET = re.compile(r"\[(\d{1,3})\]")

QUALITY_RANK = {"2160p": 4, "1080p": 3, "720p": 2, "480p": 1, "360p": 0}


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
        "isBatch": is_batch or episode is None,
    }


def _score(rel):
    """Skor pemilihan: seeders utama, kualitas penyeimbang."""
    q = QUALITY_RANK.get((rel.get("quality") or "").lower(), 0)
    trusted = 500 if rel.get("trusted") else 0
    return (rel.get("seeders", 0) + trusted, q)


def organize(releases):
    """Pisahkan rilis menjadi {episodes: [...terbaik per episode...], batches: [...]}.

    Setiap episode menyimpan SATU rilis terbaik; jumlah alternatif dicatat.
    Batch diurutkan dari seeders terbanyak.
    """
    by_ep = {}
    alt_count = {}
    batches = []
    for rel in releases:
        info = parse_release(rel.get("rawTitle", ""))
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
