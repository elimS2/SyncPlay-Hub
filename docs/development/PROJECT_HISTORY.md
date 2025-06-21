# Project History & Git Context

## 🎯 **Project Overview for AI Context**

This file provides structured information about the project's evolution, key architectural decisions, and important changes to help AI assistants (like Cursor IDE) understand the project context better.

**Project:** YouTube Playlist Downloader & Web Player  
**Primary File:** Originally `web_player.py` (1129 lines) → Refactored to modular architecture  
**Architecture:** Flask-based web application with SQLite database  
**Purpose:** Download YouTube playlists and serve them via local web player  

---

## 📈 **Complete Development Timeline**

### **Project Statistics**
- **Total Commits:** 65
- **Development Period:** 2025-06-16 to 2025-01-21 (extended development)
- **Latest Commit:** ec7726b - Database backup system implementation
- **Initial Import:** e299d24 - SyncPlay-Hub project inception

### **Phase 0: Project Genesis (2025-06-16)**
- `e299d24` - **Initial import** - SyncPlay-Hub project created
- `dec2eab` - **Media handling expansion** - Added support for multiple file formats
- `676215e` - **Navigation controls** - Basic player interface added
- `6d74356` - **Fullscreen & keyboard** - Enhanced user experience

### **Phase 1: UI/UX Development (2025-06-16)**
- `5eecf43` - **Custom player controls** - Replaced basic controls with custom UI
- `b256f82` - **Track loading refactor** - Better control over media loading
- `688b864` - **Playlist visibility** - Side panel functionality
- `962eca0` - **README updates** - Documentation improvements

### **Phase 2: Download System Enhancement (2025-06-16)**
- `2c8f934` - **Progress tracking** - Added _ProgLogger for download progress
- `d7c1cfe` - **Cookie authentication** - Support for age-restricted content
- Multiple commits focused on download reliability and user feedback

### **Phase 3: Advanced Features (2025-06-17 to 2025-06-19)**
- Database integration and SQLite schema development
- Web player interface refinements
- Real-time progress monitoring
- Log streaming capabilities

### **Phase 4: Recent Enhancements (2025-06-20)**
- `05bab04` - **Static log serving** - `/static_log` endpoint with security
- `ba01dc5` - **Download tracking** - Active downloads with status updates
- `705031e` - **Quick scan functionality** - Enhanced metadata fetching
- `2d1242c` - **Trash management** - Move deleted files to Trash/ instead of permanent deletion
- `ec7726b` - **Database backup system** - Complete backup functionality with web interface

---

## 🏗️ **Major Architectural Phases**

### **Phase 1: Monolithic Architecture (Original)**
- **Single file:** `web_player.py` (~1129 lines)
- **Everything in one place:** Routes, business logic, utilities, streaming
- **Global variables:** Direct management of state
- **Working but hard to maintain**

### **Phase 2: Modular Refactoring (Current)**
- **Separated concerns:** `app.py`, `controllers/`, `services/`, `utils/`
- **Clean architecture:** Each module has specific responsibility
- **Better maintainability:** Easier to test and modify
- **Preserved functionality:** All original features maintained

### **Development Intensity**
- **63 commits in 4 days** - Extremely rapid development cycle
- **From concept to production** - Complete working system
- **Feature-rich MVP** - Full functionality in minimal time
- **Iterative improvement** - Constant refinement and enhancement

---

## 📚 **Key Components & Their Evolution**

### **Core Application**
- `web_player.py` → `app.py` (main Flask application)
- Moved from 1129 lines to ~300 lines focused structure
- Preserved all routes and functionality

### **Download Management**
- Originally inline in `web_player.py`
- Now: `services/download_service.py` + `controllers/api_controller.py`
- **Key insight:** Active downloads tracking moved to service layer

### **Database Operations**
- Always separate: `database.py` (unchanged)
- Used by: `scan_to_db.py` (unchanged)
- Integration maintained in new architecture

### **Logging System**
- Originally inline classes in `web_player.py`
- Now: `utils/logging_utils.py`
- **Key classes:** `AnsiCleaningStream`, `DualStreamHandler`

### **Streaming System**
- Complex state management originally in `web_player.py`
- Preserved in `app.py` with identical functionality
- **Critical:** STREAMS global dict and client management

---

## 🔧 **Critical Architectural Decisions**

### **1. ROOT_DIR Management**
- **Issue:** Path handling for media files
- **Solution:** ROOT_DIR = PLAYLISTS_DIR (not base directory)
- **Impact:** Fixes media serving `/media/TopMusic6/file.webm`

### **2. Template Data Compatibility**
- **Issue:** Templates expect specific data structures
- **Solution:** Services return same format as original
- **Example:** `get_active_downloads()` returns `Dict[str, dict]` not `List[dict]`

### **3. API Compatibility**
- **Preserved:** All endpoint signatures and responses
- **Moved:** Implementation to `controllers/api_controller.py`
- **Maintained:** Error handling and JSON responses

---

## 🚨 **Critical Issues Resolved**

### **Issue #1: Template Rendering Error**
- **Date:** 2025-01-21
- **Error:** `'list object' has no attribute 'items'`
- **Root Cause:** `get_active_downloads()` return type mismatch
- **Solution:** Changed service to return `Dict[str, dict]` not `List[dict]`
- **Files:** `services/download_service.py`, `templates/playlists.html`

### **Issue #2: ANSI Codes in Log Files**
- **Status:** Previously resolved
- **Problem:** Console colors bleeding into log files
- **Solution:** `AnsiCleaningStream` class properly implemented

### **Issue #3: Media Serving Paths**
- **Status:** Previously resolved  
- **Problem:** Wrong ROOT_DIR causing 404 errors
- **Solution:** ROOT_DIR = PLAYLISTS_DIR not base directory

---

## 📊 **Current Status (2025-01-21)**

### **Architecture Verification: 100% Complete**
- ✅ All components working
- ✅ Templates rendering correctly
- ✅ API endpoints functional
- ✅ Media serving operational
- ✅ Database operations working
- ✅ Streaming system functional

### **Code Quality**
- ✅ All code in English (language policy enforced)
- ✅ Modular architecture implemented
- ✅ Documentation organized (`docs/` structure)
- ✅ Development logging established

---

## 🔍 **File Relationships & Dependencies**

### **Import Flow**
```
app.py
├── controllers/api_controller.py
│   ├── services/download_service.py
│   ├── services/playlist_service.py
│   └── services/streaming_service.py (future)
├── utils/logging_utils.py
├── database.py
└── templates/*.html
```

### **Data Flow**
```
User Request → Flask Route (app.py) → Controller (controllers/) → Service (services/) → Database (database.py) → Response
```

### **Template Dependencies**
- `playlists.html` expects `active_downloads` as `Dict[str, dict]`
- `index.html` expects `playlist_rel` and `server_ip`
- All templates preserved from original architecture

---

## 🎛️ **Configuration & Environment**

### **Data vs Code Separation**
- **Code:** `C:\Users\eL\Dropbox\Programming\CursorProjects\Youtube\`
- **Data:** `D:\music\Youtube\` (configurable with `--root`)
- **Structure:** `<root>/Playlists/`, `<root>/DB/`, `<root>/Logs/`

### **Key Environment Details**
- **Python:** 3.11
- **Framework:** Flask
- **Database:** SQLite (`tracks.db`)
- **Media:** Downloaded via `yt-dlp`
- **Serving:** Local network (`0.0.0.0:8000`)

---

## 🧪 **Testing Context**

### **Known Working Scenarios**
- ✅ Playlist downloads and sync
- ✅ Web player functionality
- ✅ Database scanning (`scan_to_db.py`)
- ✅ Media file serving
- ✅ Real-time log streaming
- ✅ Active download tracking

### **Testing Data**
- **Real database:** 669 tracks, 406 play events
- **Real media:** 75-316MB files in multiple playlists
- **Real usage:** Tested with actual YouTube playlists

---

## 💡 **For AI Assistants: Key Context**

### **When Making Changes**
1. **Check original:** Compare with `web_player.py` for reference
2. **Preserve interfaces:** Templates and APIs expect specific formats
3. **Test with real data:** Use actual media files and database
4. **Log changes:** Use `DEVELOPMENT_LOG.md` format
5. **Verify paths:** ROOT_DIR and media serving critical

### **Common Patterns**
- **Error handling:** Use `abort(404)` not exceptions for user errors
- **JSON responses:** `{"status": "ok/error", "message": "..."}`
- **Path security:** Always use `_ensure_subdir()` for user paths
- **Database:** Connection management via `get_connection()`

### **Architecture Principle**
> "Preserve original functionality while improving code organization"

---

## 📈 **Future Considerations**

### **Potential Improvements**
- API documentation generation
- Unit tests for critical components
- Configuration file system
- Plugin architecture for new features

### **Stability Priority**
- **Don't break:** Existing templates and APIs
- **Preserve:** All original functionality
- **Document:** Every change in development log

---

*This file is maintained to provide AI assistants with comprehensive project context.* 