# Development Guidelines for YouTube Playlist Downloader

## 🎯 **Project Overview**
This document outlines the development rules and guidelines for contributing to the YouTube Playlist Downloader project.

---

## 🌍 **Language Policy**

### **Code Language (MANDATORY)**
All source code **MUST** be written exclusively in **English**:

- ✅ **Variables, functions, classes:** `playlist_name`, `download_status`, `MediaPlayer`
- ✅ **Comments and documentation:** `# Download the playlist metadata`
- ✅ **String literals:** `"Download completed successfully"`
- ✅ **Commit messages:** `fix: resolve template rendering error`
- ✅ **Error messages:** `FileNotFoundError: Playlist directory not found`
- ✅ **Logging:** `logger.info("Starting playlist sync")`
- ✅ **API responses:** `{"status": "success", "message": "Scan completed"}`

### **Communication Language**
- **Developer communication** can be in any language (Russian, English, etc.)
- **Code must remain English** regardless of communication language
- **Assistant responses** match the developer's query language

### **Enforcement Rules**
1. **Never inject non-English** languages into code
2. **Translate existing non-English** code to English when modifying
3. **All new code** follows English-only conventions
4. **Priority:** Code quality and international standards take precedence

---

## 🏗️ **Architecture Guidelines**

### **Project Structure**
Follow the established modular architecture:
```
project/
├── app.py                    # Main Flask application
├── controllers/              # API controllers (Flask routes)
├── services/                 # Business logic
├── utils/                    # Utility functions
├── templates/                # Jinja2 templates
├── static/                   # CSS, JS, images
└── docs/                     # Documentation
```

### **Separation of Concerns**
- **Controllers** handle HTTP requests/responses
- **Services** contain business logic
- **Utils** provide reusable helper functions
- **Templates** handle presentation layer

### **Code vs Data Separation**
- **Code directory:** `<PROJECT_ROOT>/` (git repository)
- **Data directory:** `<DATA_ROOT>/` (user data, configurable)
- **Server runs with:** `python app.py --root "<DATA_ROOT>"`

---

## 🔧 **Development Standards**

### **Code Quality**
- **Follow PEP 8** for Python code style
- **Use type hints** where appropriate: `def get_playlist(name: str) -> Dict[str, Any]:`
- **Write docstrings** for functions and classes
- **Handle exceptions** properly with specific error types

### **Import Organization**
```python
# Standard library imports
import os
import json
from pathlib import Path

# Third-party imports
from flask import Flask, request, jsonify
import sqlite3

# Local imports
from services.playlist_service import get_playlists
from utils.logging_utils import log_message
```

### **Function Naming**
- **Public functions:** `get_active_downloads()`, `scan_library()`
- **Private functions:** `_ensure_subdir()`, `_format_file_size()`
- **API endpoints:** `api_playlists()`, `api_event()`

---

## 📋 **Development Documentation Policy**

### **🚨 IMPORTANT: Development Log Maintenance Discontinued**

**As of 2025-07-06, development log maintenance has been discontinued to reduce overhead and token consumption.**

### **New Documentation Approach**

#### **Use Detailed Commit Messages**
Instead of maintaining separate development logs, use comprehensive commit messages:

**Prompt for AI Assistant:**
```
"Give an exhaustive, detailed comment for the commit, I will copy-paste it and make the commit"
```

**Example Detailed Commit Message:**
```
feat: implement comprehensive trash management system

- Add trash statistics API endpoint (/api/trash_stats)
- Implement clear trash functionality with confirmation (/api/clear_trash)
- Add trash size calculation with recursive directory scanning
- Create UI section in deleted tracks page with modern card layout
- Add confirmation dialog with multi-step validation
- Preserve database records while removing physical files
- Update can_restore flag to prevent restoration of cleared files
- Add error handling for permission issues and missing directories
- Implement loading states and user feedback for operations
- Format file sizes with human-readable units (B, KB, MB, GB)

Technical details:
- Uses shutil.rmtree() for efficient directory cleanup
- Implements graceful error handling for file system operations
- Maintains data integrity by preserving audit trail in database
- Follows REST API patterns with proper HTTP status codes
- Includes comprehensive input validation and sanitization

Impact: Provides disk space management while maintaining data safety
Files: controllers/api/channels_api.py, templates/deleted.html
```

#### **Access Development History**
Use git commands to review development history:
```bash
# Recent commits overview
git log --oneline -10

# Detailed commit history
git log --stat -5

# Full changes with diffs
git log -p -3

# Commits in date range
git log --since="2025-07-01" --until="2025-07-10"

# Search commits by keyword
git log --grep="trash" --oneline

# Show specific commit details
git show <commit_hash>
```

### **Benefits of New Approach**
- ✅ **Reduced overhead** - No time spent on log maintenance
- ✅ **Token efficiency** - No large log files to process
- ✅ **Better git integration** - History directly in version control
- ✅ **Searchable** - Use git commands to find specific changes
- ✅ **Atomic** - Each commit contains complete change description
- ✅ **Standardized** - Follows conventional commit message format

### **Commit Message Guidelines**
- **Type**: feat, fix, docs, refactor, test, style, chore
- **Scope**: Optional, e.g., `feat(api): add new endpoint`
- **Description**: Detailed explanation of what and why
- **Body**: Technical details, impact analysis, testing notes
- **Footer**: Breaking changes, issue references

### **🔧 Git Commands Without Pager (PowerShell & Terminal)**

#### **RECOMMENDED: Use --no-pager for Git Commands**

**Problem:** In PowerShell and some terminals, git commands open a pager that blocks output
**Solution:** Use `--no-pager` flag for better compatibility

#### **Useful Git Commands:**

**Get Recent Commits:**
```bash
# Last 1, 5, 10, 20 commits
git --no-pager log --oneline -1
git --no-pager log --oneline -5  
git --no-pager log --oneline -10
git --no-pager log --oneline -20

# With dates and details
git --no-pager log --pretty="format:%h %ci %s" -10
```

**Count Total Commits:**
```bash
# Total commit count
git --no-pager rev-list --count HEAD
```

**Get Current HEAD:**
```bash
# Current commit info
git --no-pager log -1 --pretty="format:%h %ci %s"
```

**Get Commit Range:**
```bash
# Commits between dates or hashes
git --no-pager log --oneline --since="2025-06-20" --until="2025-06-22"
git --no-pager log --oneline commit1..commit2
```

#### **Why --no-pager is Useful:**
- ✅ **Works in PowerShell** - No hanging or blocking
- ✅ **Script-friendly** - Clean output for automation
- ✅ **Large outputs** - Can retrieve 30+ commits without issues
- ✅ **Consistent behavior** - Same output across different terminals
- ✅ **AI/Tool compatible** - Output directly usable in scripts

---

## 🔧 **Development Standards**

### **Code Quality**
- **Follow PEP 8** for Python code style
- **Use type hints** where appropriate: `def get_playlist(name: str) -> Dict[str, Any]:`
- **Write docstrings** for functions and classes
- **Handle exceptions** properly with specific error types

### **Import Organization**
```python
# Standard library imports
import os
import json
from pathlib import Path

# Third-party imports
from flask import Flask, request, jsonify
import sqlite3

# Local imports
from services.playlist_service import get_playlists
from utils.logging_utils import log_message
```

### **Function Naming**
- **Public functions:** `get_active_downloads()`, `scan_library()`
- **Private functions:** `_ensure_subdir()`, `_format_file_size()`
- **API endpoints:** `api_playlists()`, `api_event()`

---

## 🧪 **Testing Guidelines**

### **Manual Testing**
- **Test all API endpoints** after changes
- **Verify template rendering** in browser
- **Check logs** for errors or warnings
- **Test with real data** from user directory

### **Error Handling**
- **Use appropriate HTTP status codes:** 200, 404, 500
- **Return JSON errors:** `{"status": "error", "message": "Description"}`
- **Log errors** with context: `logger.error(f"Failed to process {playlist_name}: {str(e)}")`

---

## 📝 **Documentation Standards**

### **Code Documentation**
```python
def get_active_downloads() -> Dict[str, dict]:
    """Get dictionary of all active downloads with runtime information.
    
    Returns:
        Dict[str, dict]: Dictionary with task_id as key and task info as value.
            Each task contains: title, url, type, status, runtime, etc.
    """
```

### **Commit Messages**
Follow conventional commits format:
- `feat: add playlist streaming functionality`
- `fix: resolve template rendering error with active_downloads`
- `docs: update API documentation`
- `refactor: extract download logic to service layer`

### **Issue Documentation**
When fixing bugs, document in `DEVELOPMENT_LOG.md`:
- **Problem description** with error messages
- **Root cause analysis** 
- **Considered solutions** with pros/cons
- **Implemented solution** with code changes
- **Testing results**

---

## 🔄 **Refactoring Guidelines**

### **Interface Compatibility**
- **Maintain existing APIs** during refactoring
- **Preserve template data structures** 
- **Keep database schema** unless absolutely necessary
- **Test thoroughly** after changes

### **Before Making Changes**
1. **Read existing documentation** (`REFACTORING_CHECKLIST.md`, `DEEP_VERIFICATION_PLAN.md`)
2. **Understand the original implementation** (compare with `web_player.py`)
3. **Plan the change** with consideration for existing integrations
4. **Document the change** in development log

### **Common Pitfalls**
- ❌ Changing return types without updating templates
- ❌ Breaking API compatibility
- ❌ Not testing with real user data
- ❌ Forgetting to update documentation

---

## 🛠️ **IDE Configuration**

### **Cursor IDE**
- Configuration is in `.cursorrules` file (project root)
- Rules are automatically applied during development
- Assistant follows these guidelines automatically

### **Recommended Extensions**
- Python syntax highlighting
- Flask/Jinja2 template support
- SQLite database viewer
- Git integration

---

## 🚀 **Deployment Guidelines**

### **Environment Setup**
```bash
# Install dependencies
pip install -r requirements.txt

# Set up data directory structure
mkdir -p /path/to/data/{Playlists,DB,Logs}

# Run server
python app.py --root "/path/to/data"
```

### **Configuration**
- **Data directory** should be separate from code directory
- **Logs** are written to `<DATA_ROOT>/Logs/`
- **Database** is at `<DATA_ROOT>/DB/tracks.db`
- **Media files** are in `<DATA_ROOT>/Playlists/`

---

## 📚 **Related Documentation**

- **[Development Log](DEVELOPMENT_LOG.md)** - Historical reference (discontinued)
- **[Project History](PROJECT_HISTORY.md)** - Historical reference (discontinued)
- **[Refactoring Checklist](REFACTORING_CHECKLIST.md)** - Code comparison progress
- **[Deep Verification Plan](DEEP_VERIFICATION_PLAN.md)** - Testing methodology
- **[Main README](../../README.md)** - Project overview and usage

**Note:** Development logs are no longer maintained. Use `git log` for development history.

---

## ✅ **Quick Checklist for Contributors**

Before submitting changes:
- [ ] All code is in English
- [ ] Functions have proper docstrings
- [ ] Error handling is implemented
- [ ] Templates render correctly
- [ ] APIs return expected data structures
- [ ] **Use detailed commit message** with comprehensive description
- [ ] Commit message includes: what, why, technical details, impact
- [ ] Manual testing completed
- [ ] Commit message follows conventional commit format
- [ ] All changes are properly tested and verified

---

*This document should be updated whenever development practices change.*