"""Main API router combining all modular endpoints."""

from flask import Blueprint

# Import shared components and initialize
from .shared import init_api_controller

# Import all module blueprints
from .base_api import base_bp
from .playlist_api import playlist_bp
from .volume_api import volume_bp
from .seek_api import seek_bp
from .browser_api import browser_bp
from .streaming_api import streaming_bp
from .system_api import system_bp
from .remote_api import remote_bp
from .channels_api import channels_bp
from .jobs_api import jobs_bp
from .backup_api import backup_bp
from .metadata_api import metadata_bp
from .cleanup_api import cleanup_bp
from .trash_api import trash_bp
from .tracks_api import tracks_bp

# Create main API blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Register all module blueprints
api_bp.register_blueprint(base_bp)
api_bp.register_blueprint(playlist_bp)
api_bp.register_blueprint(volume_bp)
api_bp.register_blueprint(seek_bp)
api_bp.register_blueprint(browser_bp)
api_bp.register_blueprint(streaming_bp)
api_bp.register_blueprint(system_bp)
api_bp.register_blueprint(remote_bp)
api_bp.register_blueprint(channels_bp)
api_bp.register_blueprint(jobs_bp)
api_bp.register_blueprint(backup_bp)
api_bp.register_blueprint(metadata_bp)
api_bp.register_blueprint(cleanup_bp)
api_bp.register_blueprint(trash_bp)
api_bp.register_blueprint(tracks_bp)

def init_api_router(root_dir, thumbnails_dir=None):
    """Initialize the API router with root and optional thumbnails directory."""
    init_api_controller(root_dir, thumbnails_dir)

# Export main blueprint for app registration
__all__ = ['api_bp', 'init_api_router'] 