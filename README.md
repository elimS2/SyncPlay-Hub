# YouTube Playlist Downloader

# SyncPlay-Hub

> Local-first downloader & web-player for YouTube playlists

---

## Motivation

YouTube's shuffle works poorly on large playlists—especially on smart-TV apps, where it often randomises only the first ~100 items and repeats them.  
I wanted a way to:

1. Download the **entire** playlist (audio-only or full video) to a local drive.  
2. Keep the folder in sync when I add / remove songs on YouTube.  
3. Avoid YouTube's *cover-only cascade* – on some devices if the playlist encounters a track that has no real video (just a static album cover), **all subsequent clips keep showing the cover** even when full videos are available.  
4. Play the library on any device in my LAN (TV, tablet, phone) with proper shuffle, next/prev, etc.

That idea evolved into **SyncPlay-Hub**: a small Python toolset powered by `yt-dlp` + Flask.

---

## Features

* Reliable playlist sync (detects additions/removals; preserves "unavailable" videos as archive).  
* Fast / safe modes, live progress counter.  
* Cookie support for age-restricted or region-blocked videos.  
* Responsive web player with custom controls and adaptive dark/light theme.  
* Keyboard shortcuts & TV-friendly UI (playlist hides in fullscreen).
* Add new playlists straight from the web UI – downloads start in the background and appear automatically when finished.
* "Forgotten" metric on the homepage – highlights tracks that were never played or haven't been heard in the last 30 days, helping you rediscover neglected songs.

---

## Requirements

* Python 3.9+
* [`ffmpeg`](https://ffmpeg.org/) available in your `PATH` (only needed when extracting audio)
* All Python dependencies listed in `requirements.txt` (installed automatically in the next step)

---

## Installation

```bash
# 1. Clone (or download) this repository
# 2. Enter the project directory and install Python dependencies
pip install -r requirements.txt
```

> 💡 On Windows you can use PowerShell; on macOS/Linux use your preferred shell.

---

## Basic usage

### 1) Download audio only (MP3)
```bash
python download_playlist.py "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx" \
       --output MyMusic --audio-only
```
* All tracks will be saved inside a sub-folder named after the playlist, e.g., `MyMusic/Chill Beats/My Song [dQw4w9WgXcQ].mp3`.
* Re-running the same command will **skip** files that are already present (check `downloaded.txt`).
* Files that you have removed from the playlist on YouTube are also deleted locally on the next run (unless you pass `--no-sync`).

### 2) Download full videos (best quality)
```bash
python download_playlist.py "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx" \
       --output MyVideos
```
* The script grabs the best available video + audio stream and stores it as `Title [VIDEO_ID].mp4` under `MyVideos/<Playlist Title>/` (container decided by `yt-dlp`).
* Local files whose IDs are no longer in the playlist are removed automatically. If the video is unavailable online, the file is kept and its ID is stored in `unavailable_ids.txt`. Should the video ever become public again, the file will be treated normally on the next run (i.e., deleted if still absent from the playlist). Use `--no-sync` to skip any deletion.

### 3) Extra flags

* `--no-sync` – keep local files even if they were removed from the playlist online (disables any deletion step).
* `--debug` – show full yt-dlp output and internal progress (useful for troubleshooting cookies or network issues).

---

## Authentication / age-restricted videos

Some playlist items may be gated by age, region or "sign-in to confirm". Pass your own YouTube cookies so yt-dlp can access them.

### 1) Import cookies automatically (Chrome/Edge/Firefox)

```bash
python download_playlist.py <URL> --use-browser-cookies
```

### 2) Export cookies.txt manually and pass path

```bash
# export via browser extension, then:
python download_playlist.py <URL> --cookies C:\path\youtube_cookies.txt
```

If both flags are provided, `--cookies` has priority.

---

## Advanced notes

* The naming template can be adjusted directly in `download_playlist.py` (variable `output_template`). Default structure: `<playlist>/Title [VIDEO_ID].ext`.
* For private playlists you need to export cookies and pass them using `--cookies ~/cookies.txt`; refer to the `yt-dlp` documentation.

---

## Local web player

The repository ships with a lightweight **Flask** application that turns every folder with media files into a web-player accessible from any device in your LAN (TV, phone, tablet, laptop).

### Launch

```bash
# Serve everything under D:\Media on port 8000, accessible on your local network
python web_player.py --root "D:\Media" --host 0.0.0.0 --port 8000
```

Open `http://<your_ip>:8000/` in a modern browser – the UI is responsive and works on both desktop and mobile.

### File discovery

* Recursively scans **audio _and_ video** formats: `mp3`, `m4a`, `opus`, `webm`, `flac`, `mp4`, `mkv`, `mov`.
* Keeps the original folder structure so albums / live-shows remain grouped.

### Player highlights

| Area | Details |
|------|---------|
| **Queue logic** | Auto-shuffle on first load, manual Shuffle button, click-to-play, automatic next-track on end |
| **Smart Shuffle** | New algorithm prioritises never-played tracks, then oldest (year→month→week→day) – accessible via button and used by default |
| **Controls** | Prev · Play/Pause · Next · Mute/Volume · Seekbar · Timestamps · Fullscreen |
| **Keyboard** | `← / →` previous / next, `Space` play/pause |
| **Mouse / touch** | Click on video toggles play/pause; click on progress bar seeks |
| **Playlist panel** | 600 px wide, custom scrollbar, hamburger button (`☰`) to hide/show; panel hides automatically in fullscreen |
| **Casting** | Built-in Google Cast support – plays on Chromecast / Android TV; local IP is injected to avoid "localhost" issues |
| **Media Session API** | Integrates with OS media keys and lock-screen controls |
| **Theming** | Dark/Light via `prefers-color-scheme`; colours centralised in CSS variables |

All client logic lives in **`static/player.js`** – extend, re-skin or integrate with external APIs as you wish.

---

## Playback statistics & database

Starting from v0.2 the project includes a lightweight **SQLite** database automatically created under a `DB/` sub-folder next to your `Playlists/` media directory. It stores:

* Track metadata (duration, size, bitrate, etc.)
* Per-track counters: starts, finishes, *next* / *prev* skips
* Per-track **likes** – counted via ❤️ button (only one like per track per 12 h)
* Timestamps of the last start / finish event
* Full play history (every start / finish / skip / like event with position)

### How it works

1. Run the library scan once: `python scan_to_db.py --root <base_dir>` where `<base_dir>` **must** contain two sub-folders:
   * `Playlists/` – your media folders
   * `DB/` – will be auto-created if missing and will hold `tracks.db`
2. Start the web server: `python web_player.py --root <base_dir>`
3. Open the browser UI – the header includes:
   * **Rescan Library** – rescans folders and updates the database without CLI
   * **Track Library** – paginated table with all tracks and counters
   * **Play History** – paginated log (1000 rows/page) of all playback events (freshest first)

> Stats are updated in real-time while you interact with the player: starting a track, skipping to next/previous, reaching the end of playback.

### Database schema (v0.3)

SQLite file: `tracks.db`

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `playlists` | One row per local playlist folder | `id` PK · `name` · `relpath` UNIQUE · `track_count` · `last_sync_ts` · `source_url` |
| `tracks` | Unique entry for each YouTube video / audio file | `id` PK · `video_id` UNIQUE · `name` · `relpath` · `duration` · `size_bytes` · playback counters |
| `track_playlists` | Many-to-many link between tracks and playlists | composite PK (`track_id`,`playlist_id`) |
| `play_history` | Immutable log of all user events | `id` PK · `video_id` · `event` (`start`/`finish`/`next`/`prev`/`like`/`removed`) · `ts` · `position` |

This design keeps track statistics even if a file is removed from every playlist: the file's row in `tracks` remains, only the linking rows in `track_playlists` are deleted. If the same YouTube video re-appears later, it will reuse the existing stats.

---

## Logs & monitoring

Each background download writes its full terminal output to `Logs/<Playlist>.log` next to your `Playlists/` and `DB/` folders.  
From the homepage click **Logs** – you will see a list of all log files. Selecting any log opens a real-time view (similar to `tail -F`) streamed via Server-Sent Events; new lines appear instantly in your browser as the download progresses.

This is useful to track long downloads or troubleshoot failures without having to open the server console.