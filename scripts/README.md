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
  ```

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