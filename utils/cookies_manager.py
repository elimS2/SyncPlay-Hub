"""
Cookies Management Utility for YouTube Downloader

This module provides functionality to automatically select and validate
random cookie files from a specified directory for yt-dlp operations.
"""

import os
import random
import glob
from pathlib import Path
from typing import Optional, List
import logging

# Configure logger
logger = logging.getLogger(__name__)


def get_cookies_directory() -> Optional[Path]:
    """
    Get cookies directory from environment variable or default location.
    
    Returns:
        Path to cookies directory or None if not configured/found
    """
    # Check environment variable first
    cookies_env = os.environ.get('YOUTUBE_COOKIES_DIR')
    if cookies_env:
        cookies_path = Path(cookies_env)
        if cookies_path.exists() and cookies_path.is_dir():
            logger.info(f"Using cookies directory from environment: {cookies_path}")
            return cookies_path
        else:
            logger.warning(f"Cookies directory from environment not found: {cookies_path}")
    
    # Check default location (same as provided in the query)
    default_path = Path("D:/music/Youtube/Cookies")
    if default_path.exists() and default_path.is_dir():
        logger.info(f"Using default cookies directory: {default_path}")
        return default_path
    
    logger.info("No cookies directory found")
    return None


def find_cookie_files(cookies_dir: Path) -> List[Path]:
    """
    Find all cookie files in the specified directory.
    
    Args:
        cookies_dir: Path to cookies directory
        
    Returns:
        List of cookie file paths
    """
    if not cookies_dir.exists() or not cookies_dir.is_dir():
        return []
    
    # Common cookie file patterns
    patterns = [
        "*.txt",
        "*.cookies",
        "*cookies*",
        "youtube*.txt",
        "*.json"  # Some browser extensions export as JSON
    ]
    
    cookie_files = []
    for pattern in patterns:
        cookie_files.extend(cookies_dir.glob(pattern))
    
    # Remove duplicates and filter only files
    unique_files = []
    seen_files = set()
    for file_path in cookie_files:
        if file_path.is_file() and file_path not in seen_files:
            unique_files.append(file_path)
            seen_files.add(file_path)
    
    logger.debug(f"Found {len(unique_files)} cookie files in {cookies_dir}")
    return unique_files


def validate_cookies_file(cookie_path: Path) -> bool:
    """
    Validate if the cookie file is valid for YouTube.
    
    Args:
        cookie_path: Path to cookie file
        
    Returns:
        True if valid, False otherwise
    """
    try:
        if not cookie_path.exists() or not cookie_path.is_file():
            return False
            
        # Check file size (empty files are invalid)
        if cookie_path.stat().st_size == 0:
            return False
            
        # Read and check content
        with open(cookie_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(4096)  # Read first 4KB
            
        # Check for YouTube-specific content
        youtube_indicators = [
            '.youtube.com',
            'youtube',
            'consent.youtube.com',
            'accounts.google.com'
        ]
        
        content_lower = content.lower()
        has_youtube_content = any(indicator in content_lower for indicator in youtube_indicators)
        
        if not has_youtube_content:
            logger.debug(f"Cookie file {cookie_path.name} does not contain YouTube cookies")
            return False
            
        logger.debug(f"Cookie file {cookie_path.name} is valid")
        return True
        
    except Exception as e:
        logger.warning(f"Error validating cookie file {cookie_path}: {e}")
        return False


def get_random_cookie_file() -> Optional[str]:
    """
    Get a random valid cookie file from the configured cookies directory.
    
    Returns:
        String path to cookie file or None if no valid cookies found
    """
    cookies_dir = get_cookies_directory()
    if not cookies_dir:
        return None
    
    cookie_files = find_cookie_files(cookies_dir)
    if not cookie_files:
        logger.info(f"No cookie files found in {cookies_dir}")
        return None
    
    # Filter valid cookie files
    valid_cookies = []
    for cookie_file in cookie_files:
        if validate_cookies_file(cookie_file):
            valid_cookies.append(cookie_file)
    
    if not valid_cookies:
        logger.warning(f"No valid cookie files found in {cookies_dir}")
        return None
    
    # Select random cookie file
    selected_cookie = random.choice(valid_cookies)
    logger.info(f"Selected random cookie file: {selected_cookie.name} ({len(valid_cookies)} available)")
    
    return str(selected_cookie)


def get_cookies_for_download(explicit_path: Optional[str] = None, use_browser: bool = False) -> tuple[Optional[str], bool]:
    """
    Get cookies configuration for download operations.
    
    Args:
        explicit_path: Explicitly provided cookie file path
        use_browser: Whether to use browser cookies
        
    Returns:
        Tuple of (cookie_path, should_use_browser)
    """
    # Priority 1: Explicit path provided
    if explicit_path:
        logger.info(f"Using explicitly provided cookie file: {explicit_path}")
        return explicit_path, False
    
    # Priority 2: Browser cookies requested
    if use_browser:
        logger.info("Using browser cookies as requested")
        return None, True
    
    # Priority 3: Try to get random cookie file from directory
    random_cookie = get_random_cookie_file()
    if random_cookie:
        return random_cookie, False
    
    # Priority 4: Fallback to browser cookies if available
    logger.info("No cookie files available, checking browser cookies fallback")
    return None, False


def log_cookies_status() -> None:
    """Log current cookies configuration status."""
    logger.info("=== Cookies Configuration Status ===")
    
    cookies_dir = get_cookies_directory()
    if cookies_dir:
        cookie_files = find_cookie_files(cookies_dir)
        valid_count = sum(1 for f in cookie_files if validate_cookies_file(f))
        
        logger.info(f"Cookies directory: {cookies_dir}")
        logger.info(f"Total cookie files found: {len(cookie_files)}")
        logger.info(f"Valid cookie files: {valid_count}")
        
        if valid_count > 0:
            logger.info("Random cookie selection: ENABLED")
        else:
            logger.warning("Random cookie selection: DISABLED (no valid cookies)")
    else:
        logger.info("Cookies directory: NOT CONFIGURED")
        logger.info("Random cookie selection: DISABLED")
    
    # Check environment variable
    env_path = os.environ.get('YOUTUBE_COOKIES_DIR')
    if env_path:
        logger.info(f"Environment variable YOUTUBE_COOKIES_DIR: {env_path}")
    else:
        logger.info("Environment variable YOUTUBE_COOKIES_DIR: NOT SET")


if __name__ == "__main__":
    # Test the functionality
    logging.basicConfig(level=logging.INFO)
    
    print("Testing cookies manager...")
    log_cookies_status()
    
    random_cookie = get_random_cookie_file()
    if random_cookie:
        print(f"Random cookie selected: {random_cookie}")
    else:
        print("No random cookie available") 