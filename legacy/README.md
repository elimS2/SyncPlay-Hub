# Legacy Code Archive

This directory contains legacy code files that have been replaced by the new modular architecture but are preserved for reference and historical context.

## Files

### `web_player.py` (1,129 lines)
**Original monolithic Flask application** - The complete original implementation before refactoring.

**Replaced by:**
- `app.py` - Main Flask application (streamlined)
- `controllers/api_controller.py` - API endpoints
- `services/download_service.py` - Download management
- `services/playlist_service.py` - Playlist operations
- `services/streaming_service.py` - Streaming functionality
- `utils/logging_utils.py` - Logging utilities

**Why preserved:**
- **Reference implementation** - Contains the complete working logic
- **Refactoring validation** - Used to verify new architecture maintains all functionality
- **Bug fixing** - Original behavior can be checked when issues arise
- **Documentation** - Shows the evolution from monolithic to modular design

**Key features that were preserved:**
- All Flask routes and API endpoints
- Active downloads tracking with `ACTIVE_DOWNLOADS` dict
- Streaming system with `STREAMS` global state
- Dual logging system (console + file)
- Media serving with proper path handling
- Database integration and operations

### `log_utils.py` (34 lines)
**Original logging utility** - Simple print() monkey-patching for timestamp+PID prefixes.

**Replaced by:**
- `utils/logging_utils.py` - Comprehensive logging system with ANSI cleaning, dual streams, and Flask integration

**Why preserved:**
- **Simple approach** - Shows the original lightweight logging solution
- **Migration reference** - Helps understand the logging evolution
- **Fallback option** - Could be used if complex logging causes issues

## Architecture Evolution

### Phase 1: Monolithic (Original)
```
web_player.py (1,129 lines)
├── All Flask routes
├── Business logic
├── Database operations
├── Streaming system
├── Download management
├── Logging utilities
└── Static file serving
```

### Phase 2: Modular (Current)
```
app.py (305 lines)
├── controllers/
│   └── api_controller.py
├── services/
│   ├── download_service.py
│   ├── playlist_service.py
│   └── streaming_service.py
├── utils/
│   └── logging_utils.py
├── database.py (unchanged)
├── templates/ (unchanged)
└── static/ (unchanged)
```

## Usage Guidelines

### For Developers
1. **Reference only** - Do not modify files in this directory
2. **Comparison tool** - Use when implementing new features to ensure compatibility
3. **Bug investigation** - Check original behavior when debugging issues
4. **Architecture understanding** - Study the evolution from monolithic to modular

### For AI Assistants
1. **Context preservation** - These files provide historical context for the project
2. **Interface compatibility** - New architecture must maintain the same external interfaces
3. **Functionality verification** - All features from original must be preserved
4. **Code patterns** - Original patterns should be followed when extending functionality

## Migration Status

- ✅ **Complete** - All functionality successfully migrated to new architecture
- ✅ **Tested** - New architecture verified to work with real data
- ✅ **Compatible** - All APIs and templates maintain same interface
- ✅ **Documented** - Migration process documented in development logs

## Removal Timeline

These files will be kept indefinitely for:
- Historical reference
- Architecture documentation
- Debugging support
- Educational purposes

**Note:** If the project proves stable for 6+ months without needing legacy reference, these files may be moved to a separate archive repository. 