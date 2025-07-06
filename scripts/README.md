# Scripts Directory

This directory contains command-line interface (CLI) scripts and tools for the YouTube Playlist Downloader project.

## Available Scripts

### 📊 Metadata Management
- **`extract_channel_metadata.py`** - Extract YouTube channel metadata and store in database
  ```bash
  python scripts/extract_channel_metadata.py "https://www.youtube.com/@ChannelName/videos"
  python scripts/extract_channel_metadata.py "URL" --dry-run  # Test mode
  ```

### 🔍 Analysis Tools
- **`channel_download_analyzer.py`** - Analyze channel download status and compare with metadata
  ```bash
  python scripts/channel_download_analyzer.py                    # Analyze all channels
  python scripts/channel_download_analyzer.py --channel-id 1     # Specific channel
  python scripts/channel_download_analyzer.py --group-id 2       # All channels in group
  python scripts/channel_download_analyzer.py --days-back 30     # Last 30 days only
  python scripts/channel_download_analyzer.py --summary-only     # Just summaries
  ```

- **`list_channels.py`** - List all channels and groups with their IDs
  ```bash
  python scripts/list_channels.py                               # List all groups and channels
  python scripts/list_channels.py --groups-only                 # List only groups
  python scripts/list_channels.py --db-path "D:/path/tracks.db" # Use specific database
  ```

### Database Management
- `database_audit.py` - Audit database for tracks with missing files
- `restore_missing_tracks.py` - Automatically restore missing tracks with stable paths

### Channel Management
- `cleanup_channel_metadata.py` - Clean up channel metadata
- `scan_missing_metadata.py` - Scan for tracks with missing metadata

## Script Categories

### 🎯 **CLI Tools** (Interactive/Standalone)
Scripts that can be run independently from command line for specific tasks.

**Current Location:** Root directory (to be moved here)
- `download_playlist.py` - Download YouTube playlists
- `scan_to_db.py` - Scan local files and update database
- `download_content.py` - Download content with advanced options

### 🔧 **Maintenance Scripts**
- `update_channel_stats.py` - Update channel statistics
- `restart_server.py` - Server management

### 📦 **Migration Scripts**
- `migrate_playlist_events.py` - Database migration for playlist events
- `migrate_playlist_events_with_dates.py` - Migration with date handling

### 🗂️ **Utility Scripts**  
- `check_laud_channel.py` - Channel-specific operations
- `clear_kola_archive.py` - Archive cleanup

### 🔍 **Analysis Scripts**
- `channel_download_analyzer.py` - Analyze download status vs metadata
- `list_channels.py` - List channels and groups with IDs

## Recommended Organization

```
scripts/
├── README.md                           # This file
├── metadata/
│   └── extract_channel_metadata.py    # Metadata extraction tools
├── analysis/
│   ├── channel_download_analyzer.py   # Download status analysis
│   └── list_channels.py               # Channel listing utility
├── download/
│   ├── download_playlist.py           # Download tools
│   └── download_content.py
├── database/
│   ├── scan_to_db.py                  # Database operations
│   └── migrate_*.py                   # Migration scripts
├── maintenance/
│   ├── update_channel_stats.py        # Maintenance tasks
│   └── restart_server.py
└── utilities/
    ├── check_laud_channel.py          # Specific utilities
    └── clear_kola_archive.py
```

## Database Configuration

Scripts need to know where your `tracks.db` file is located. By default, they look for `tracks.db` in the current directory, but you can specify a different location:

### Option 1: .env file (Recommended)
```bash
# Create .env file in project root
echo "DB_PATH=D:/music/Youtube/DB/tracks.db" > .env

# Scripts automatically load it
python scripts/list_channels.py  # Will show: 📄 Loaded .env file from: .env
```

### Option 2: Command Line Argument
```bash
python scripts/list_channels.py --db-path "D:/music/Youtube/DB/tracks.db"
python scripts/channel_download_analyzer.py --db-path "D:/music/Youtube/DB/tracks.db"
```

See [`ENV_SETUP.md`](ENV_SETUP.md) for detailed configuration instructions.

## Usage Guidelines

### Running Scripts
```bash
# From project root
python scripts/extract_channel_metadata.py [args]

# With module path (if needed)
python -m scripts.extract_channel_metadata [args]
```

### Development Guidelines
1. **All CLI scripts should be executable independently**
2. **Use argparse for command-line arguments**
3. **Include --help documentation**
4. **Use existing logging system (utils.logging_utils)**
5. **Follow error handling patterns from existing scripts**
6. **Include dry-run modes where appropriate**

### Integration with Project
- Scripts can import from project modules: `from database import ...`
- Use unified logging: `from utils.logging_utils import log_message`
- Follow existing database connection patterns
- Maintain backwards compatibility for existing automation

## Future Organization
Consider moving all CLI scripts from root to this directory for better project organization while maintaining backwards compatibility through wrapper scripts or path adjustments.

## Missing Tracks Restoration

The `restore_missing_tracks.py` script automatically restores tracks that exist in the database but are missing from disk. It uses a stable directory structure based on YouTube Channel IDs to prevent issues with channel/folder renames and integrates with the job queue system.

### Features

- **Stable Path Structure**: Uses `PLAYLISTS_DIR/YouTube_Channel_ID/video_file` format
- **Job Queue Integration**: Creates download jobs instead of direct downloads
- **Priority System**: Prioritizes tracks with likes and high play counts
- **Batch Processing**: Can restore multiple tracks with progress tracking
- **Dry Run Mode**: Test what would be restored without creating jobs
- **Configuration Support**: Reads settings from `.env` file

### Usage Examples

```bash
# Restore all missing tracks with priority for liked tracks
python scripts/restore_missing_tracks.py

# Restore only top 10 missing tracks
python scripts/restore_missing_tracks.py --max-tracks 10

# Dry run - show what would be restored
python scripts/restore_missing_tracks.py --dry-run

# Restore without priority for liked tracks
python scripts/restore_missing_tracks.py --no-priority

# Specify custom paths
python scripts/restore_missing_tracks.py --db-path "D:/music/Youtube/DB/tracks.db" --playlists-dir "D:/music/Youtube/Playlists"
```

### Directory Structure

After restoration, tracks are organized as:
```
PLAYLISTS_DIR/
├── UC1234567890abcdef/  # Channel ID 1
│   ├── Song Title 1 [video_id1].mp4
│   └── Song Title 2 [video_id2].mp4
├── UC9876543210fedcba/  # Channel ID 2
│   ├── Another Song [video_id3].mp4
│   └── Yet Another [video_id4].mp4
└── ...
```

### Benefits

- **Rename-Resistant**: Channel name changes don't affect file paths
- **Organized**: Files grouped by channel for easy management
- **Traceable**: Channel ID in path allows easy identification
- **Consistent**: All restored tracks follow the same structure
- **Job Queue Integration**: Downloads managed by the job system with monitoring

### Configuration

The script reads configuration from `.env` file:
- `DB_PATH` - Database file path
- `PLAYLISTS_DIR` - Directory for storing playlists
- `ROOT_DIR` - Root directory (fallback for PLAYLISTS_DIR)

### Prerequisites

- Python 3.6+
- `yt-dlp` installed (`pip install yt-dlp`)
- Job queue system running
- Valid YouTube cookies (recommended for better success rate)

## Environment Setup

See `ENV_SETUP.md` for detailed environment configuration instructions. 