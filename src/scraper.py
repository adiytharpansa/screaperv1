"""screaperv1 — scraper katalog anime: metadata AniList + torrent Nyaa.si.

Pemakaian:
  python -m src.scraper --title "Sousou no Frieren"
  python -m src.scraper --id 154587
  python -m src.scraper --file titles.txt        (baku bila tanpa --title/--id)
  python -m src.scraper --title "..." --trusted  (hanya rilis trusted Nyaa)

Keluaran:
  output/catalog.json         — semua judul, digabung per anilistId
  output/titles/<id>.json     — satu berkas per judul

Struktur tiap judul: metadata AniList utuh + torrents.episodes
(rilis terbaik per episode: magnet, .torrent, infoHash, seeders,
ukuran, kualitas, grup rilis) + torrents.batches.
"""
import argparse
import datetime
import json
import pathlib
import sys
import time

from . import anilist, matcher, nyaa

ROOT = pathlib.Path(__file__).resolve().parent.parent


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sweep_episode(names, episode, expected_season, trusted_only=False):
    """Cari SATU episode dengan query khusus. Urutan coba:
    'Judul - 05' (romaji) -> 'Judul - 05' (inggris) -> 'Judul 05' (romaji).
    Mengembalikan entri rilis terbaik atau None."""
    romaji = names[0] if names else ""
    english = names[1] if len(names) > 1 else ""
    queries = []
    if romaji:
        queries.append(f"{romaji} - {episode:02d}")
    if english and english != romaji:
        queries.append(f"{english} - {episode:02d}")
    if romaji:
        queries.append(f"{romaji} {episode:02d}")
    for query in queries:
        try:
            found = nyaa.search(query, trusted_only=trusted_only)
        except Exception:
            found = []
        candidates = matcher.filter_episode(found, episode, expected_season)
        if candidates:
            best = matcher.best_of(candidates)
            best["alternatives"] = len(candidates) - 1
            best["viaSweep"] = True
            return best
        time.sleep(0.8)
    return None


def build_entry(meta, trusted_only=False, per_episode=True, max_sweep=60):
    names = []
    for key in ("romaji", "english", "native"):
        value = (meta.get("title") or {}).get(key)
        if value and value not in names:
            names.append(value)
    romaji = (meta.get("title") or {}).get("romaji") or ""
    expected_season = matcher.season_of(romaji) or 1

    releases = nyaa.search_title(names, trusted_only=trusted_only)
    torrents = matcher.organize(releases, expected_season=expected_season)

    total = meta.get("episodesTotal")
    found_eps = {e["episode"] for e in torrents["episodes"]}
    missing = ([ep for ep in range(1, total + 1) if ep not in found_eps]
               if total else [])
    sweep_capped = False
    if per_episode and total:
        missing = [ep for ep in range(1, total + 1) if ep not in found_eps]
        if len(missing) > max_sweep:
            sweep_capped = True
            missing_sweep = missing[:max_sweep]
        else:
            missing_sweep = missing
        for ep in missing_sweep:
            best = sweep_episode(names, ep, expected_season, trusted_only=trusted_only)
            if best is not None:
                torrents["episodes"].append(best)
                found_eps.add(ep)
            time.sleep(0.8)
        torrents["episodes"].sort(key=lambda e: e["episode"])
        missing = [ep for ep in range(1, total + 1) if ep not in found_eps]

    entry = dict(meta)
    entry["torrents"] = torrents
    entry["nyaaReleaseCount"] = len(releases)
    entry["episodeCoverage"] = {
        "total": total,
        "found": len(torrents["episodes"]),
        "missing": missing,
        "seasonAssumed": expected_season,
        "sweepCapped": sweep_capped,
    }
    entry["updatedAt"] = utc_now()
    return entry


def load_catalog(out_dir):
    path = out_dir / "catalog.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {e["anilistId"]: e for e in data if e.get("anilistId")}
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def save(out_dir, entries_by_id):
    out_dir.mkdir(parents=True, exist_ok=True)
    titles_dir = out_dir / "titles"
    titles_dir.mkdir(parents=True, exist_ok=True)
    catalog = sorted(entries_by_id.values(), key=lambda e: e.get("anilistId") or 0)
    (out_dir / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    for entry in catalog:
        (titles_dir / f"{entry['anilistId']}.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog


def main(argv=None):
    ap = argparse.ArgumentParser(prog="screaperv1")
    ap.add_argument("--title", help="satu judul (dicari di AniList)")
    ap.add_argument("--id", type=int, help="ID AniList langsung")
    ap.add_argument("--file", default=str(ROOT / "titles.txt"),
                    help="berkas daftar judul, satu per baris")
    ap.add_argument("--out", default=str(ROOT / "output"), help="folder keluaran")
    ap.add_argument("--trusted", action="store_true", help="hanya rilis trusted Nyaa")
    ap.add_argument("--no-per-episode", action="store_true",
                    help="matikan sapuan per-episode (hanya pencarian umum)")
    ap.add_argument("--max-sweep", type=int, default=60,
                    help="maksimum episode hilang yang disapu per judul")
    args = ap.parse_args(argv)

    out_dir = pathlib.Path(args.out)
    entries = load_catalog(out_dir)

    jobs = []  # list of ("title", str) / ("id", int)
    if args.title:
        jobs.append(("title", args.title))
    elif args.id:
        jobs.append(("id", args.id))
    else:
        path = pathlib.Path(args.file)
        if not path.exists():
            print(f"Berkas judul tidak ditemukan: {path}", file=sys.stderr)
            return 2
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                jobs.append(("title", line))

    if not jobs:
        print("Tidak ada pekerjaan: beri --title, --id, atau isi titles.txt", file=sys.stderr)
        return 2

    failures = 0
    for kind, value in jobs:
        try:
            meta = anilist.fetch_by_title(value) if kind == "title" else anilist.fetch_by_id(value)
            if not meta:
                print(f"[LEWAT] AniList tidak menemukan: {value}")
                failures += 1
                continue
            entry = build_entry(meta, trusted_only=args.trusted,
                                per_episode=not args.no_per_episode,
                                max_sweep=args.max_sweep)
            entries[entry["anilistId"]] = entry
            t = entry["torrents"]
            cov = entry["episodeCoverage"]
            print(f"[OK] {entry['title'].get('romaji')} (AniList {entry['anilistId']}): "
                  f"episode {cov['found']}/{cov['total']}, {len(t['batches'])} batch, "
                  f"{entry['nyaaReleaseCount']} rilis Nyaa, hilang: {cov['missing']}")
        except Exception as e:  # satu judul gagal tidak menjatuhkan sisanya
            failures += 1
            print(f"[GAGAL] {value}: {e}", file=sys.stderr)
        time.sleep(1)

    catalog = save(out_dir, entries)
    print(f"Katalog tersimpan: {len(catalog)} judul -> {out_dir / 'catalog.json'}")
    return 1 if failures and failures == len(jobs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
