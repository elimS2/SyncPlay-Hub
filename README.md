# YouTube Playlist Downloader

# SyncPlay-Hub

> Local-first downloader & web-player for YouTube playlists

---

## Motivation

YouTube's shuffle works poorly on large playlists—especially on smart-TV apps, where it often randomises only the first ~100 items and repeats them.  
I wanted a way to:

1. Download the **entire** playlist (audio-only or full video) to a local drive.  
2. Keep the folder in sync when I add / remove songs on YouTube.  
3. Play the library on any device in my LAN (TV, tablet, phone) with proper shuffle, next/prev, etc.

That idea evolved into **SyncPlay-Hub**: a small Python toolset powered by `yt-dlp` + Flask.

---

## Features

* Reliable playlist sync (detects additions/removals; preserves "unavailable" videos as archive).  
* Fast / safe modes, live progress counter.  
* Cookie support for age-restricted or region-blocked videos.  
* Responsive web player with custom controls and adaptive dark/light theme.  
* Keyboard shortcuts & TV-friendly UI (playlist hides in fullscreen).

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

The project ships with a tiny Flask application that lets you browse, shuffle and play your downloaded tracks directly in the browser.

### Launch

```bash
# Example: serve everything that was downloaded to D:\music\Youtube on port 8000
python web_player.py --root "D:\music\Youtube" --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/` (or the corresponding host/port) in any modern browser.

### Features

* Recursively scans the given root folder for audio files (.mp3/.m4a/.opus/.webm/.flac).
* Displays them in a list; click to play any track.
* "Shuffle & Play" button randomises the queue and starts playback.
* Automatically advances to the next track when the current one ends.
* All implemented client-side in `static/player.js`; feel free to extend UI/UX.

### Controls & features

* Custom control bar (Prev · Play/Pause · Next · Mute/Volume · Seekbar · Time · Fullscreen).
* Keyboard shortcuts: `← / →` – previous / next, `Space` – play/pause.
* Playlist sits to the right of the video (auto-hides when entering fullscreen).
* Dark/light theme adapts to OS (`prefers-color-scheme`).

### Sync tips

By default the downloader performs a **full metadata scan** of your playlist to ensure accurate deletion logic. This can take 1–2 min for very large lists, but the CLI shows a live counter:

```
[Info] Playlist contains ~206 items. Starting detailed scan…
  …parsed 57/206 entries
```

If you prefer speed over safety, run with `--no-sync` and clean up manually later.