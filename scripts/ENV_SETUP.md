# Environment Setup

## Database Path Configuration

The analysis scripts can automatically find your database using .env files or command-line arguments.

### Option 1: .env file (Recommended)

Create a `.env` file in the project root for automatic loading:

**Create `.env` file in project root:**
```bash
# Copy and customize this example:
cat > .env << 'EOF'
# YouTube Playlist Downloader Configuration
DB_PATH=D:/music/Youtube/DB/tracks.db
ROOT_DIR=D:/music/Youtube
PLAYLISTS_DIR=D:/music/Youtube/Playlists
LOGS_DIR=D:/music/Youtube/Logs

# Cookies Configuration (optional - enables automatic random cookie selection)
YOUTUBE_COOKIES_DIR=D:/music/Youtube/Cookies

# Proxy Configuration (optional - helps bypass YouTube blocking)
# PROXY_URL=http://proxy.example.com:8080
# PROXY_URL=socks5://127.0.0.1:1080
EOF
```

**Or manually create `.env` file with:**
```
DB_PATH=D:/music/Youtube/DB/tracks.db
ROOT_DIR=D:/music/Youtube
PLAYLISTS_DIR=D:/music/Youtube/Playlists
LOGS_DIR=D:/music/Youtube/Logs

# Cookies Configuration (optional - enables automatic random cookie selection)
YOUTUBE_COOKIES_DIR=D:/music/Youtube/Cookies

# Proxy Configuration (optional - helps bypass YouTube blocking)
# PROXY_URL=http://proxy.example.com:8080
# PROXY_URL=socks5://127.0.0.1:1080
```

**The scripts will automatically load this file if:**
- `.env` file exists in project root
- You'll see: `📄 Loaded .env file from: /path/to/.env`

### Option 2: Command Line Argument

```bash
python scripts/list_channels.py --db-path "D:/music/Youtube/DB/tracks.db"
python scripts/channel_download_analyzer.py --db-path "D:/music/Youtube/DB/tracks.db"
```

## Usage Examples

```bash
# With .env file (automatic)
python scripts/list_channels.py
python scripts/channel_download_analyzer.py

# Or specify path directly
python scripts/list_channels.py --db-path "D:/music/Youtube/DB/tracks.db"
python scripts/channel_download_analyzer.py --db-path "D:/music/Youtube/DB/tracks.db"
```

## Common Database Locations

- **Default**: `./tracks.db` (current directory)
- **Common**: `D:/music/Youtube/DB/tracks.db`
- **Alternative**: `~/Downloads/Youtube/DB/tracks.db`

The scripts will show which database they're using when they start. 