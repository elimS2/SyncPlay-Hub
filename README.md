# YouTube Playlist Downloader

# SyncPlay-Hub

> Local-first downloader & web-player for YouTube playlists

## 🏗️ Project Structure

**CRITICAL: Code and Data Separation**

This project uses a **strict separation** between code and user data:

- **📁 Code Directory**: `<PROJECT_ROOT>\`
  - Contains: `app.py`, `controllers/`, `services/`, `utils/`, `templates/`, `static/`
  - This is where you edit code, run git commands, etc.

- **📁 User Data Directory**: `<DATA_ROOT>\`
  - Contains: database `DB\tracks.db`, logs `Logs\`, playlists `Playlists\`
  - Server runs with: `python app.py --root "<DATA_ROOT>"`

**⚠️ Important for Development:**
- When testing database: check `<DATA_ROOT>\DB\tracks.db`, NOT local `tracks.db`
- Server logs write to `<DATA_ROOT>\Logs\`
- Media files are in `<DATA_ROOT>\Playlists\`

## ⚠️ Development Rules

**IMPORTANT**: This project follows strict language conventions:

- **ALL CODE** must be written in **English only**
- This includes: variables, functions, comments, strings, commit messages, error messages
- Communication with developers can be in any language, but code remains English
- See `.cursorrules` and `CURSOR_RULES.md` for complete details

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
* Spreadsheet-style homepage: sortable columns (Tracks, Plays, Likes, Forgotten, Last Sync) with one-click **Resync** and **Link** actions.
* One-click **Rescan Library** to update metadata without touching the CLI.
* **Database Backup System** – create timestamped backups of your entire database with one click, preserving all track metadata, play statistics, and history safely.

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
* Files that you have removed from the playlist on YouTube are moved to a `Trash/` folder locally on the next run (unless you pass `--no-sync`). The trash preserves the original playlist folder structure.

### 2) Download full videos (best quality)
```bash
python download_playlist.py "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx" \
       --output MyVideos
```
* The script grabs the best available video + audio stream and stores it as `Title [VIDEO_ID].mp4` under `MyVideos/<Playlist Title>/` (container decided by `yt-dlp`).
* Local files whose IDs are no longer in the playlist are moved to trash automatically. If the video is unavailable online, the file is kept and its ID is stored in `unavailable_ids.txt`. Should the video ever become public again, the file will be treated normally on the next run (i.e., moved to trash if still absent from the playlist). Use `--no-sync` to skip any file management.

### 3) Extra flags

* `--no-sync` – keep local files even if they were removed from the playlist online (disables any file management).
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

### Homepage at a glance

The first page you open shows an overview table of every playlist in your collection:

| Column | What it tells you | Why it matters |
|--------|------------------|----------------|
| **Playlist** | Folder name (clickable) | Jump straight to the track-view |
| **Tracks** | File count after the last sync | Quick size estimate |
| **Plays** | Total starts / skips / finishes | Popularity indicator |
| **Likes** | ❤️ counts from all tracks | Favourite density |
| **Forgotten** | Tracks never played or silent for ≥30 days | Perfect queue for rediscovery |
| **Last Sync** | Timestamp of the last successful download | See if you're up-to-date |

Every header is **click-to-sort** – two clicks switch between ascending / descending, so you can instantly surface the most popular playlists, or those with the most neglected tracks.

Action buttons:

* **Resync** – re-download a linked playlist in background and refresh the DB.
* **Link** – attach an existing folder to a YouTube playlist URL (enables future Resync).
* **Rescan Library** (top-bar) – walk the filesystem & refresh stats without touching downloads.

Additions and resyncs run fully in background; progress logs stream in real-time under the **Logs** section.

---

## Server Management

### Server Control Features

The web interface includes built-in server management tools accessible from the main page:

* **🔄 Restart Server** – Restarts the Flask server process in the same console window
* **🛑 Stop Server** – Gracefully shuts down the server without closing the console
* **Server Info Display** – Shows current PID, start time, and uptime

These controls are useful for:
- Applying configuration changes without manual console access
- Managing the server remotely from any device on your network
- Troubleshooting without interrupting the console session

### Centralized Logging

All server activity is logged to a unified log file system:

- **Main log**: `Logs/SyncPlay-Hub.log` – Contains all server events, HTTP requests, and system messages
- **Download logs**: `Logs/<Playlist>.log` – Individual logs for each playlist download/sync operation
- **Real-time streaming**: View logs live in your browser with automatic updates
- **Clean formatting**: ANSI color codes are stripped from file logs while preserved in console output
- **Log rotation**: Automatic rotation at 10MB with 5 backup files to prevent disk space issues

### Log Management Interface

The **Logs** page provides a comprehensive view of all log files:

| Column | Description |
|--------|-------------|
| **File Name** | Log file name (clickable to view) |
| **Last Modified** | When the log was last updated |
| **Size** | Human-readable file size (B, KB, MB, GB) |

Features:
- **Sortable columns** – Click headers to sort by name, date, or size
- **Default sorting** – Newest files appear first automatically  
- **Main log highlighting** – `SyncPlay-Hub.log` is visually distinguished
- **Real-time viewing** – Click any log file for live streaming view

---

## Database Backup System

The application includes a comprehensive backup system to protect your valuable music library data.

### Creating Backups

**From Web Interface:**
- Click **"💾 Backup DB"** button on the main page
- Or visit the **Backups** page and click **"Create New Backup"**

**Backup Process:**
1. Creates timestamped folder in `Backups/DB/YYYYMMDD_HHMMSS_UTC/`
2. Uses SQLite's built-in backup API for consistency
3. Records backup event in play history
4. Returns backup size and location

### Backup Contents

Each backup preserves:
- **All track metadata** – titles, durations, file sizes, bitrates
- **Play statistics** – start/finish counts, likes, last played times
- **Playlist relationships** – which tracks belong to which playlists
- **Complete play history** – every playback event with timestamps
- **Database structure** – tables, indexes, and constraints

### Backup Management

**Backups Page Features:**
- **Sortable table** – by date, size, or backup ID
- **Storage overview** – total backups count and disk usage
- **File information** – creation time and file size for each backup
- **Quick actions** – create new backups or refresh the list

**Backup Location:**
```
root/
└── Backups/
    └── DB/
        ├── 20250121_143000_UTC/
        │   └── tracks.db        # 2.5 MB backup
        └── 20250121_150000_UTC/
            └── tracks.db        # 2.6 MB backup
```

### Restoration

To restore from a backup:
1. Stop the server
2. Navigate to `Backups/DB/[timestamp]/`
3. Copy `tracks.db` to your main `DB/` folder
4. Restart the server

### Best Practices

- **Regular backups** – Create backups before major changes
- **Before updates** – Backup before software updates
- **Storage management** – Periodically clean old backups to save space
- **Verification** – Check backup file sizes are reasonable (typically 1-10 MB)

---

## API Endpoints

The web player exposes several API endpoints for programmatic control:

### Playlist Management
- `GET /api/playlists` – List all playlists with metadata
- `POST /api/add_playlist` – Add new playlist from YouTube URL
- `POST /api/resync` – Resync existing playlist with YouTube
- `POST /api/link_playlist` – Link local folder to YouTube URL

### Track & Playback
- `GET /api/tracks/<path>` – Get tracks for specific playlist
- `POST /api/event` – Record playback events (start, finish, skip, like)
- `POST /api/scan` – Trigger library rescan

### Server Control
- `POST /api/restart` – Restart server process
- `POST /api/stop` – Stop server gracefully

### Database Backup
- `POST /api/backup` – Create new database backup
- `GET /api/backups` – List all available backups

### Live Streaming
- `GET /api/streams` – List active streaming sessions
- `POST /api/create_stream` – Create new streaming session
- `POST /api/stream_event/<id>` – Send events to streaming session
- `GET /api/stream_feed/<id>` – Server-sent events feed for streaming

---

## File Structure

```
project-root/
├── app.py                  # Main Flask application
├── download_playlist.py    # YouTube playlist downloader
├── scan_to_db.py          # Library scanner for database
├── database.py            # SQLite database operations
├── restart_server.py      # Server restart helper
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── .cursorrules          # Cursor IDE rules
├── controllers/          # API controllers
│   ├── __init__.py
│   └── api_controller.py # API endpoint handlers
├── services/             # Business logic services
│   ├── __init__.py
│   ├── download_service.py  # Download management
│   ├── playlist_service.py  # Playlist operations
│   └── streaming_service.py # Streaming functionality
├── utils/                # Utilities
│   ├── __init__.py
│   └── logging_utils.py  # Centralized logging system
├── docs/                 # Documentation
│   ├── README.md         # Documentation index
│   ├── development/      # Development documentation
│   │   ├── DEVELOPMENT_LOG.md    # Issue tracking & fixes
│   │   ├── PROJECT_HISTORY.md    # Git history & AI context
│   │   ├── CURSOR_RULES.md       # Development guidelines
│   │   ├── REFACTORING_CHECKLIST.md # Code comparison
│   │   └── DEEP_VERIFICATION_PLAN.md # Testing methodology
│   └── user/             # User documentation (future)
├── legacy/               # Legacy code archive
│   ├── README.md         # Legacy files documentation
│   ├── web_player.py     # Original monolithic app (1,129 lines)
│   └── log_utils.py      # Original logging utility
├── static/               # Web assets
│   ├── player.js         # Main player JavaScript
│   └── stream_client.js  # Streaming client code
└── templates/            # HTML templates
    ├── index.html        # Main player interface
    ├── playlists.html    # Playlist overview
    ├── tracks.html       # Track library
    ├── history.html      # Play history
    ├── logs.html         # Log file browser
    ├── log_view.html     # Individual log viewer
    ├── streams.html      # Streaming sessions
    ├── stream_view.html  # Stream player
    └── backups.html      # Database backup management
```

### Data Directory Structure

When you run the application, it expects this structure in your `--root` directory:

```
media-root/
├── Playlists/            # Your downloaded media files
│   ├── Playlist1/        # Individual playlist folders
│   │   ├── Song1 [ID].mp3
│   │   └── Song2 [ID].mp4
│   └── Playlist2/
│       └── Video [ID].webm
├── Trash/                # Removed files (auto-created)
│   ├── Playlist1/        # Maintains original playlist structure
│   │   └── Removed Song [ID].mp3
│   └── Playlist2/
│       └── Removed Video [ID].webm
├── Backups/              # Database backups (auto-created)
│   └── DB/               # Database backup storage
│       ├── 20250121_143000_UTC/
│       │   └── tracks.db # Timestamped backup
│       └── 20250121_150000_UTC/
│           └── tracks.db # Another backup
├── DB/                   # Database files (auto-created)
│   └── tracks.db         # SQLite database
└── Logs/                 # Log files (auto-created)
    ├── SyncPlay-Hub.log  # Main server log
    └── Playlist1.log     # Download logs per playlist
```

---

## Troubleshooting

### Common Issues

**Server won't start on specified port**
- Check if another application is using the port: `netstat -an | findstr :8000`
- Try a different port: `python web_player.py --port 8001`

**Can't access from other devices**
- Ensure you're using `--host 0.0.0.0` (not `127.0.0.1`)
- Check firewall settings on the host machine
- Verify devices are on the same network

**Downloads fail with "Sign in to confirm your age"**
- Export YouTube cookies and use `--cookies` flag
- Or use `--use-browser-cookies` for automatic cookie import

**Media files not appearing in player**
- Run library rescan: click "Rescan Library" in web interface
- Or manually: `python scan_to_db.py --root <your-root-directory>`
- Check file extensions are supported (see File discovery section)

**Database corruption or migration issues**
- Backup your `DB/tracks.db` file
- Delete the database file to recreate it
- Run `python scan_to_db.py --root <root>` to rebuild

### Debug Mode

For detailed troubleshooting information:

```bash
# Enable debug output for downloads
python download_playlist.py <URL> --debug

# Check server logs in real-time
# Open http://localhost:8000/logs and click on SyncPlay-Hub.log
```

### Performance Tips

- **Large libraries**: The initial scan may take time. Subsequent scans only process changed files.
- **Network streaming**: Use wired connection for the server when possible for better streaming performance.
- **Storage**: Consider SSD storage for better seek performance with large video files.

---

## Contributing

This project follows strict development guidelines:

1. **All code must be in English** – variables, functions, comments, strings, commit messages
2. **Use consistent formatting** – Follow existing code style
3. **Test changes** – Verify both download and web player functionality
4. **Update documentation** – Keep README.md current with new features

See `CURSOR_RULES.md` and `.cursorrules` for complete development guidelines.

---

## License

This project is provided as-is for personal use. Please respect YouTube's Terms of Service and only download content you have the right to access.