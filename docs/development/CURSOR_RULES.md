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

## 📋 **Development Logging (MANDATORY)**

### **Automatic Documentation Requirement**
**EVERY** code modification must be immediately documented in `DEVELOPMENT_LOG.md`. No exceptions.

### **When to Log**
- ✅ **After every code edit** - functions, classes, variables, imports
- ✅ **Configuration changes** - settings, environment variables  
- ✅ **Bug fixes** - even small ones
- ✅ **Refactoring** - code structure improvements
- ✅ **New features** - functionality additions
- ✅ **Template changes** - HTML, CSS, JavaScript modifications
- ✅ **Database changes** - schema, queries, migrations

### **Log Entry Format**
Each entry must follow this structure:

```markdown
### Log Entry #XXX - YYYY-MM-DD HH:MM
**Change:** [Brief description of what was changed]

#### Files Modified
- `path/to/file1.py` - [what changed]
- `path/to/file2.html` - [what changed]

#### Reason for Change
[Detailed explanation of WHY this change was needed]

#### What Changed
```python
# Before
old_code_example()

# After  
new_code_example()
```

#### Impact Analysis
- **Functionality:** [How does this affect existing features]
- **Performance:** [Any performance implications]
- **Compatibility:** [Breaking changes or backwards compatibility]
- **Testing:** [What needs to be tested]

#### Verification
- [ ] Code runs without errors
- [ ] Templates render correctly
- [ ] API endpoints work as expected
- [ ] No breaking changes introduced
```

### **Example Log Entry**
```markdown
### Log Entry #002 - 2025-01-21 14:30
**Change:** Fix playlist URL generation in list_playlists function

#### Files Modified
- `services/playlist_service.py` - Fixed relative path calculation

#### Reason for Change
URLs were generating with double "Playlists/" prefix causing 404 errors:
- Wrong: `/playlist/Playlists/TopMusic6` 
- Correct: `/playlist/TopMusic6`

#### What Changed
```python
# Before
rel = str(d.relative_to(root.parent))  # "Playlists/TopMusic6"

# After
rel = d.name  # "TopMusic6"
```

#### Impact Analysis
- **Functionality:** Fixed broken playlist navigation links
- **Performance:** No impact
- **Compatibility:** No breaking changes
- **Testing:** All playlist links now work correctly

#### Verification
- [x] Code runs without errors
- [x] Templates render correctly  
- [x] Playlist links navigate properly
- [x] No breaking changes introduced
```

### **Logging Workflow**
1. **Make code change**
2. **Immediately create log entry** in `DEVELOPMENT_LOG.md`
3. **Test the change**
4. **Update verification checklist** in log entry
5. **Check git history synchronization** (see below)
6. **Commit both code and log** together

### **Benefits of Logging**
- **Traceability** - Know why every change was made
- **Debugging** - Quickly find when issues were introduced
- **Knowledge Transfer** - New developers understand decisions
- **Change Impact** - See connections between modifications

---

## 🔄 **Git History Synchronization (MANDATORY)**

### **Automatic Git Synchronization**
**EVERY** time you edit `DEVELOPMENT_LOG.md`, you **MUST** check if all git commits are documented in `PROJECT_HISTORY.md`.

### **When to Synchronize**
- ✅ **After adding development log entry** - Check for new commits
- ✅ **Before committing changes** - Ensure history is complete
- ✅ **After git pulls/merges** - Check for team commits
- ✅ **Weekly reviews** - Periodic synchronization checks

### **Synchronization Process**

#### **Step 1: Get Current Git Log**
```bash
# Get recent commits not in PROJECT_HISTORY.md
git log --pretty=format:"%h %ad %s" --date=short -10

# Count total commits
git rev-list --count HEAD
```

#### **Step 2: Compare with PROJECT_HISTORY.md**
Check if recent commits are documented in:
- `## 📈 **Complete Development Timeline**`
- Appropriate development phase sections
- Latest commit hash should match HEAD

#### **Step 3: Add Missing Commits**
```markdown
### **Phase X: [Current Phase] (YYYY-MM-DD)**
- `[commit_hash]` - **[Feature name]** - [Brief description]
```

### **🚨 Git Integration Workflow (MANDATORY - NO EXCEPTIONS)**

#### **CRITICAL TRIGGER: After EVERY DEVELOPMENT_LOG.md Edit**
**IMMEDIATE MANDATORY ACTIONS:**
1. **MUST RUN:** `git log -1 --oneline` (no exceptions)
2. **MUST CHECK:** Find this commit in PROJECT_HISTORY.md timeline
3. **IF MISSING:** Add to appropriate development phase immediately
4. **MUST UPDATE:** Total commits count in PROJECT_HISTORY.md

**⚠️ FAILURE TO FOLLOW THIS WORKFLOW IS A CRITICAL RULE VIOLATION**

#### **Standard Git Workflow (Before Each Commit):**
1. **Check current HEAD:** `git log -1 --oneline`
2. **Verify in PROJECT_HISTORY.md:** Find this commit in timeline
3. **If missing:** Add to appropriate phase
4. **Update statistics:** Total commits count

#### **Example Missing Commit Detection:**
```bash
# Current HEAD
git log -1 --pretty=format:"%h %s"
# Output: abc1234 Fix template rendering error

# Check PROJECT_HISTORY.md - if abc1234 not found:
# ADD TO PROJECT_HISTORY.md:
```
```markdown
### **Phase 5: Bug Fixes & Improvements (2025-01-21)**
- `abc1234` - **Template error fix** - Resolve active_downloads.items() issue
```

### **PROJECT_HISTORY.md Maintenance**

#### **Structure to Maintain:**
```markdown
## 📈 **Complete Development Timeline**

### **Project Statistics**
- **Total Commits:** [CURRENT_COUNT] ← Update this!
- **Development Period:** 2025-06-16 to [CURRENT_DATE]
- **Latest Commit:** [HEAD_HASH] - [HEAD_MESSAGE]

### **Phase 0: Project Genesis (2025-06-16)**
### **Phase 1: UI/UX Development (2025-06-16)**  
### **Phase 2: Download System Enhancement (2025-06-16)**
### **Phase 3: Advanced Features (2025-06-17 to 2025-06-19)**
### **Phase 4: Recent Enhancements (2025-06-20)**
### **Phase 5: Current Development (2025-01-21)** ← Add new phases!
```

#### **Phase Classification Guidelines:**
- **Genesis:** Initial project setup and basic functionality
- **UI/UX:** Player interface and user experience improvements
- **Download System:** Download management and progress tracking
- **Advanced Features:** Database, streaming, complex functionality
- **Recent Enhancements:** Latest feature additions
- **Bug Fixes:** Error resolution and stability improvements
- **Refactoring:** Code organization and architecture changes
- **Documentation:** Documentation and development process improvements

### **Automated Checks**

#### **Quick Verification Commands:**
```bash
# Get latest 5 commits
git log --oneline -5

# Search for commit in PROJECT_HISTORY.md
grep -i "[commit_hash]" docs/development/PROJECT_HISTORY.md

# If not found - ADD TO HISTORY!
```

#### **Commit Message Analysis:**
- **feat:** → New feature (add to current development phase)
- **fix:** → Bug fix (add to bug fixes phase)
- **docs:** → Documentation (add to documentation phase)
- **refactor:** → Code refactoring (add to refactoring phase)

### **Error Prevention**

#### **Common Mistakes to Avoid:**
- ❌ Adding log entry without checking git sync
- ❌ Committing with undocumented commits in history
- ❌ Forgetting to update total commit count
- ❌ Not classifying commits into appropriate phases

#### **Quality Checks:**
- ✅ Latest commit in PROJECT_HISTORY.md matches `git log -1`
- ✅ Total commit count matches `git rev-list --count HEAD`
- ✅ All recent commits have appropriate phase classification
- ✅ Commit messages match documented descriptions

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

- **[Development Log](DEVELOPMENT_LOG.md)** - Issue tracking and fixes
- **[Refactoring Checklist](REFACTORING_CHECKLIST.md)** - Code comparison progress
- **[Deep Verification Plan](DEEP_VERIFICATION_PLAN.md)** - Testing methodology
- **[Main README](../../README.md)** - Project overview and usage

---

## ✅ **Quick Checklist for Contributors**

Before submitting changes:
- [ ] All code is in English
- [ ] Functions have proper docstrings
- [ ] Error handling is implemented
- [ ] Templates render correctly
- [ ] APIs return expected data structures
- [ ] **Changes are logged in DEVELOPMENT_LOG.md** (MANDATORY)
- [ ] Log entry includes: what, why, impact, verification
- [ ] **Git history is synchronized in PROJECT_HISTORY.md** (MANDATORY)
- [ ] Latest commits documented in appropriate development phase
- [ ] Total commit count updated in PROJECT_HISTORY.md
- [ ] Manual testing completed
- [ ] Verification checklist in log completed
- [ ] Commit message follows conventions

---

*This document should be updated whenever development practices change.*