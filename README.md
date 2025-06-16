# YouTube Playlist Downloader

A simple command-line utility powered by [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) that can download every video (or just the audio) from a public or unlisted YouTube playlist. Files are saved with a sequential index so that most media players can play them in the original order or shuffle them easily.

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