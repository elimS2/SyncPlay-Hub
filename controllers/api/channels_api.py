"""Channels API main router - combines all channel-related endpoints."""

from flask import Blueprint

# Import all channel module blueprints
from .channels_groups_api import channels_groups_bp
from .channels_management_api import channels_management_bp  
from .channels_sync_api import channels_sync_bp
from .channels_files_api import channels_files_bp

# Create main channels blueprint
channels_bp = Blueprint('channels', __name__, url_prefix='/channels')

# Register all channel module blueprints
channels_bp.register_blueprint(channels_groups_bp)
channels_bp.register_blueprint(channels_management_bp)
channels_bp.register_blueprint(channels_sync_bp)
channels_bp.register_blueprint(channels_files_bp)

# Export main blueprint for api registration
__all__ = ['channels_bp']