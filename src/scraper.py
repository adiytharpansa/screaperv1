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


def build_entry(meta, trusted_only=False):
    names = []
    for key in ("romaji", "english", "native"):
        value = (meta.get("title") or {}).get(key)
        if value and value not in names:
            names.append(value)
    releases = nyaa.search_title(names, trusted_only=trusted_only)
    torrents = matcher.organize(releases)
    entry = dict(meta)
    entry["torrents"] = torrents
    entry["nyaaReleaseCount"] = len(releases)
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
            entry = build_entry(meta, trusted_only=args.trusted)
            entries[entry["anilistId"]] = entry
            t = entry["torrents"]
            print(f"[OK] {entry['title'].get('romaji')} (AniList {entry['anilistId']}): "
                  f"{len(t['episodes'])} episode, {len(t['batches'])} batch, "
                  f"{entry['nyaaReleaseCount']} rilis Nyaa")
        except Exception as e:  # satu judul gagal tidak menjatuhkan sisanya
            failures += 1
            print(f"[GAGAL] {value}: {e}", file=sys.stderr)
        time.sleep(1)

    catalog = save(out_dir, entries)
    print(f"Katalog tersimpan: {len(catalog)} judul -> {out_dir / 'catalog.json'}")
    return 1 if failures and failures == len(jobs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
