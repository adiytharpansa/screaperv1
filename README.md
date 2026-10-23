# screaperv1

Scraper katalog anime v1 — **metadata dari AniList** + **torrent/magnet dari Nyaa.si**, digabung jadi katalog JSON. Tanpa kunci API, tanpa dependensi (hanya pustaka standar Python 3.11+).

## Cara kerja

1. **AniList** (`src/anilist.py`) — GraphQL publik: judul (romaji/inggris/native), poster HD, banner, sinopsis, jumlah episode, musim/tahun, skor, genre, studio, trailer.
2. **Nyaa.si** (`src/nyaa.py`) — RSS resmi kategori `1_2` (Anime – English-translated), diurutkan dari seeders terbanyak. Magnet disusun dari `infoHash` + tracker publik bawaan Nyaa.
3. **Matcher** (`src/matcher.py`) — mengurai nomor episode, kualitas (2160p/1080p/720p/480p), grup rilis, dan penanda musim dari judul rilis; memilih **satu rilis terbaik per episode** (seeders + kualitas + trusted), rilis batch/rentang dipisah ke `batches`. Tiga penjaga kebersihan: rilis berpenanda musim lain dibuang, rilis milik entri arc lain dibuang (sisa kata sesudah judul, mis. `: Shimetsu Kaiyuu`), dan nomor episode di luar total entri dibuang (penomoran absolut waralaba).
4. **Sapuan per-episode** (`src/scraper.py`) — sesudah pencarian umum, setiap episode yang belum punya magnet dicari dengan query khusus (`Judul - 05`, varian inggris, lalu varian grup rilis yang dikenal dari judul ini) sampai lengkap atau kuota sapuan habis (baku 60/judul, `--max-sweep`). Hasil cakupan dicatat di `episodeCoverage` tiap judul (`found/total/missing`). Matikan dengan `--no-per-episode`.

## Menjalankan

Dari GitHub (disarankan — cukup dari HP): tab **Actions → Scrape → Run workflow**.

- Kosongkan semua isian → memproses seluruh `titles.txt`
- Isi `title` → satu judul · Isi `anilist_id` → satu ID AniList · Centang `trusted` → hanya rilis trusted

Hasil otomatis di-commit balik ke folder `output/`.

Lokal:

```bash
python -m src.scraper --title "Sousou no Frieren"
python -m src.scraper --id 154587
python -m src.scraper            # semua judul di titles.txt
```

## Keluaran

- `output/catalog.json` — semua judul (digabung per `anilistId`, run ulang menimpa judul yang sama)
- `output/titles/<anilistId>.json` — satu berkas per judul

Contoh isi satu judul:

```json
{
  "anilistId": 154587,
  "title": { "romaji": "Sousou no Frieren", "english": "Frieren: Beyond Journey's End" },
  "poster": "https://s4.anilist.co/.../extraLarge.jpg",
  "episodesTotal": 28,
  "episodeCoverage": { "total": 28, "found": 27, "missing": [10] },
  "genres": ["Adventure", "Drama", "Fantasy"],
  "torrents": {
    "episodes": [
      { "episode": 1, "quality": "1080p", "group": "Erai-raws",
        "seeders": 320, "size": "1.4 GiB",
        "magnet": "magnet:?xt=urn:btih:...",
        "torrentUrl": "https://nyaa.si/download/....torrent" }
    ],
    "batches": []
  }
}
```

## Struktur

```
src/anilist.py   metadata AniList (GraphQL, retry + batas waktu)
src/nyaa.py      pencarian Nyaa.si via RSS + penyusun magnet
src/matcher.py   urai episode/kualitas/grup + pilih rilis terbaik
src/scraper.py   CLI utama + tulis katalog
titles.txt       daftar pantau (satu judul per baris)
output/          hasil scrape (catalog.json + titles/)
```
