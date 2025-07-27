/**
 * Adaptive Playlist Layout Module
 * 
 * This module provides functionality to automatically switch between
 * side-by-side and under-video playlist layouts based on screen size
 * and available space for tracks.
 */

/**
 * Determines if playlist should be shown under video based on available space
 * @param {Array} tracks - Array of track objects
 * @returns {boolean} True if playlist should be under video
 */
export function shouldShowPlaylistUnderVideo(tracks) {
  const minTracksForUnderVideo = 5;
  const minTrackHeight = 40; // Approximate height of each track item
  const playlistPadding = 80; // Padding and margins
  
  // Get actual video wrapper and controls elements
  const videoWrapper = document.getElementById('videoWrapper');
  const customControls = document.getElementById('customControls');
  const currentTrackTitle = document.getElementById('currentTrackTitle');
  const controlBar = document.getElementById('controlBar');
  
  if (!videoWrapper) {
    console.warn('⚠️ [Adaptive] Video wrapper not found');
    return false;
  }
  
  // Wait for video to be properly positioned
  const videoWrapperRect = videoWrapper.getBoundingClientRect();
  if (videoWrapperRect.height === 0) {
    console.warn('⚠️ [Adaptive] Video wrapper has no height yet');
    return false;
  }
  
  // Calculate available space more accurately
  const windowHeight = window.innerHeight;
  const videoBottom = videoWrapperRect.bottom;
  
  // Account for controls and other UI elements
  let controlsHeight = 0;
  if (customControls && customControls.offsetHeight > 0) {
    controlsHeight += customControls.offsetHeight;
    console.log(`📐 [Adaptive] Custom controls height: ${customControls.offsetHeight}px`);
  }
  if (currentTrackTitle && currentTrackTitle.offsetHeight > 0) {
    controlsHeight += currentTrackTitle.offsetHeight;
    console.log(`📐 [Adaptive] Track title height: ${currentTrackTitle.offsetHeight}px`);
  }
  if (controlBar && controlBar.offsetHeight > 0) {
    controlsHeight += controlBar.offsetHeight;
    console.log(`📐 [Adaptive] Control bar height: ${controlBar.offsetHeight}px`);
  }
  
  // Add some margin for spacing
  const totalControlsHeight = controlsHeight + 60; // Increased margin for better spacing
  
  // Calculate available height under video
  const availableHeight = windowHeight - videoBottom - totalControlsHeight;
  
  // Ensure we have at least some minimum space
  if (availableHeight < 100) {
    console.log(`📐 [Adaptive] Available height too small: ${availableHeight}px`);
    return false;
  }
  
  // Calculate how many tracks can fit under video
  const tracksThatCanFit = Math.floor((availableHeight - playlistPadding) / minTrackHeight);
  
  console.log(`📐 [Adaptive] Window height: ${windowHeight}px`);
  console.log(`📐 [Adaptive] Video bottom: ${videoBottom}px`);
  console.log(`📐 [Adaptive] Controls height: ${totalControlsHeight}px`);
  console.log(`📐 [Adaptive] Available height: ${availableHeight}px`);
  console.log(`📐 [Adaptive] Tracks that can fit: ${tracksThatCanFit}`);
  console.log(`📐 [Adaptive] Total tracks: ${tracks.length}`);
  console.log(`📐 [Adaptive] Min tracks needed: ${minTracksForUnderVideo}`);
  
  return tracksThatCanFit >= minTracksForUnderVideo && tracks.length >= minTracksForUnderVideo;
}

/**
 * Applies adaptive playlist layout based on screen size and track count
 * @param {Array} tracks - Array of track objects
 */
export function applyAdaptivePlaylistLayout(tracks) {
  const playerContainer = document.querySelector('.player-container');
  const playlistPanel = document.getElementById('playlistPanel');
  
  if (!playerContainer || !playlistPanel) {
    console.warn('⚠️ [Adaptive] Required elements not found');
    return;
  }
  
  const shouldUnderVideo = shouldShowPlaylistUnderVideo(tracks);
  const isWideScreen = window.innerWidth >= 1200;
  
  console.log(`🔄 [Adaptive] Screen width: ${window.innerWidth}px`);
  console.log(`🔄 [Adaptive] Should show under video: ${shouldUnderVideo}`);
  console.log(`🔄 [Adaptive] Is wide screen: ${isWideScreen}`);
  
  if (shouldUnderVideo && isWideScreen) {
    // Force column layout for under-video display
    playerContainer.style.flexDirection = 'column';
    playlistPanel.style.width = '100%';
    playlistPanel.style.maxHeight = '40vh';
    playlistPanel.style.order = '2';
    
    console.log('✅ [Adaptive] Applied under-video layout');
  } else {
    // Reset to default responsive behavior
    playerContainer.style.flexDirection = '';
    playlistPanel.style.width = '';
    playlistPanel.style.maxHeight = '';
    playlistPanel.style.order = '';
    
    console.log('✅ [Adaptive] Applied default responsive layout');
  }
}

/**
 * Sets up adaptive layout event listeners
 * @param {Array} tracks - Array of track objects
 * @param {Function} renderList - Function to re-render the playlist
 */
export function setupAdaptiveLayout(tracks, renderList) {
  // Apply adaptive layout on page load
  window.addEventListener('DOMContentLoaded', function() {
    // Wait a bit for tracks to load and DOM to be fully rendered
    setTimeout(() => {
      applyAdaptivePlaylistLayout(tracks);
    }, 1000); // Increased delay to ensure all elements are rendered
  });
  
  // Apply adaptive layout after window load (images, etc.)
  window.addEventListener('load', function() {
    setTimeout(() => {
      applyAdaptivePlaylistLayout(tracks);
    }, 500);
  });
  
  // Apply adaptive layout on window resize
  let resizeTimeout;
  window.addEventListener('resize', function() {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      applyAdaptivePlaylistLayout(tracks);
    }, 250);
  });
  
  // Apply adaptive layout after tracks are rendered
  if (renderList) {
    const originalRenderList = renderList;
    renderList = function() {
      originalRenderList.call(this);
      
      // Apply adaptive layout after rendering with longer delay
      setTimeout(() => {
        applyAdaptivePlaylistLayout(tracks);
      }, 300); // Increased delay to ensure DOM is updated
    };
  }
}

/**
 * Initialize adaptive layout for a player
 * @param {Object} options - Configuration options
 * @param {Array} options.tracks - Array of track objects
 * @param {Function} options.renderList - Function to re-render the playlist
 * @param {string} options.playerType - Type of player ('regular' or 'virtual')
 */
export function initializeAdaptiveLayout(options) {
  const { tracks, renderList, playerType = 'regular' } = options;
  
  console.log(`🎵 [Adaptive] Initializing adaptive layout for ${playerType} player`);
  console.log(`🎵 [Adaptive] Tracks count: ${tracks.length}`);
  
  setupAdaptiveLayout(tracks, renderList);
  
  // Apply initial layout
  setTimeout(() => {
    applyAdaptivePlaylistLayout(tracks);
  }, 100);
  
  // Add global debug function
  window.debugAdaptiveLayout = function() {
    console.log('🔍 [Adaptive Debug] Manual trigger');
    console.log(`🔍 [Adaptive Debug] Tracks: ${tracks.length}`);
    console.log(`🔍 [Adaptive Debug] Should under video: ${shouldShowPlaylistUnderVideo(tracks)}`);
    applyAdaptivePlaylistLayout(tracks);
  };
  
  // Add global force functions
  window.forceUnderVideoLayout = function() {
    const playerContainer = document.querySelector('.player-container');
    const playlistPanel = document.getElementById('playlistPanel');
    
    if (playerContainer && playlistPanel) {
      playerContainer.style.flexDirection = 'column';
      playlistPanel.style.width = '100%';
      playlistPanel.style.maxHeight = '40vh';
      playlistPanel.style.order = '2';
      console.log('✅ [Adaptive Debug] Forced under-video layout');
    }
  };
  
  window.forceSideBySideLayout = function() {
    const playerContainer = document.querySelector('.player-container');
    const playlistPanel = document.getElementById('playlistPanel');
    
    if (playerContainer && playlistPanel) {
      playerContainer.style.flexDirection = '';
      playlistPanel.style.width = '';
      playlistPanel.style.maxHeight = '';
      playlistPanel.style.order = '';
      console.log('✅ [Adaptive Debug] Forced side-by-side layout');
    }
  };
  
  console.log('🎵 [Adaptive] Debug functions available:');
  console.log('  - debugAdaptiveLayout() - Check current state');
  console.log('  - forceUnderVideoLayout() - Force under-video layout');
  console.log('  - forceSideBySideLayout() - Force side-by-side layout');
} 