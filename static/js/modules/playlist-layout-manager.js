/**
 * Playlist Layout Manager
 * 
 * Manages playlist display modes: hidden, under video, side by side
 */

import { savePlaylistLayout, loadPlaylistLayout } from './playlist-preferences.js';

// Layout modes
export const LAYOUT_MODES = {
  HIDDEN: 'hidden',
  UNDER_VIDEO: 'under_video',
  SIDE_BY_SIDE: 'side_by_side'
};

// Current layout state
let currentLayoutMode = LAYOUT_MODES.SIDE_BY_SIDE;
let currentRelpath = null;
let currentPlaylistType = 'regular';
let resizeListenerAttached = false;

function recalcUnderVideoMaxHeight() {
  try {
    const playlistPanel = document.getElementById('playlistPanel');
    if (!playlistPanel) return;
    // Compute remaining space from playlistPanel top to viewport bottom
    const rect = playlistPanel.getBoundingClientRect();
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    const styles = getComputedStyle(playlistPanel);
    const marginBottom = parseFloat(styles.marginBottom || '0') || 0;
    const bottomGap = 16 + marginBottom; // breathing space + panel bottom margin
    const available = Math.max(100, Math.floor(viewportHeight - rect.top - bottomGap - 1));
    playlistPanel.style.maxHeight = available + 'px';
    playlistPanel.style.overflowY = 'auto';
  } catch (e) {
    console.warn('⚠️ [Layout] Failed to recalc under-video maxHeight:', e);
  }
}

/**
 * Applies the specified layout mode
 * @param {string} mode - Layout mode to apply
 * @param {boolean} skipSave - Skip saving preference (for initial load)
 */
export async function applyLayoutMode(mode, skipSave = false) {
  const playerContainer = document.querySelector('.player-container');
  const playlistPanel = document.getElementById('playlistPanel');
  const toggleLayoutBtn = document.getElementById('toggleLayoutBtn');
  
  if (!playerContainer || !playlistPanel) {
    console.warn('⚠️ [Layout] Required elements not found');
    return;
  }
  
  // Reset all styles first
  playerContainer.style.flexDirection = '';
  playlistPanel.style.width = '';
  playlistPanel.style.maxHeight = '';
  playlistPanel.style.order = '';
  playlistPanel.style.display = '';
  
  switch (mode) {
    case LAYOUT_MODES.HIDDEN:
      // Hide playlist completely
      playlistPanel.style.display = 'none';
      // Ensure vertical stacking when playlist is hidden
      playerContainer.style.flexDirection = 'column';
      // Prevent page vertical scroll; internal elements manage their own scrolling
      document.documentElement.style.overflowY = 'hidden';
      document.body.style.overflowY = 'hidden';
      console.log('✅ [Layout] Applied hidden layout');
      break;
      
    case LAYOUT_MODES.UNDER_VIDEO:
      // Show playlist under video
      playlistPanel.style.display = 'flex';
      playerContainer.style.flexDirection = 'column';
      playerContainer.style.overflowX = 'hidden';
      playlistPanel.style.width = '100%';
      // Set a temporary max-height; will be recalculated precisely next tick
      playlistPanel.style.maxHeight = '40vh';
      playlistPanel.style.order = '2';
      // Prevent page vertical scroll in under-video layout
      document.documentElement.style.overflowY = 'hidden';
      document.body.style.overflowY = 'hidden';
      console.log('✅ [Layout] Applied under-video layout');
      // Recalculate to eliminate page vertical scroll while keeping internal scrolling
      setTimeout(recalcUnderVideoMaxHeight, 0);
      setTimeout(recalcUnderVideoMaxHeight, 100); // second pass after any image/video reflow
      break;
      
    case LAYOUT_MODES.SIDE_BY_SIDE:
      // Show playlist side by side with video
      playlistPanel.style.display = 'flex';
      playerContainer.style.flexDirection = 'row';
      playerContainer.style.overflowX = '';
      playlistPanel.style.width = '600px';
      playlistPanel.style.maxHeight = '70vh';
      playlistPanel.style.order = '2';
      // Restore default page scroll behavior when side-by-side
      document.documentElement.style.overflowY = '';
      document.body.style.overflowY = '';
      console.log('✅ [Layout] Applied side-by-side layout');
      break;
      
    default:
      console.warn('⚠️ [Layout] Unknown layout mode:', mode);
      return;
  }
  
  // Update button text to show current mode
  if (toggleLayoutBtn) {
    const modeText = {
      [LAYOUT_MODES.HIDDEN]: 'Playlist: Hidden',
      [LAYOUT_MODES.UNDER_VIDEO]: 'Playlist: Under',
      [LAYOUT_MODES.SIDE_BY_SIDE]: 'Playlist: Right'
    };
    toggleLayoutBtn.querySelector('span:last-child').textContent = modeText[mode];
  }
  
  currentLayoutMode = mode;
  
  // Save layout preference (unless this is initial load)
  if (!skipSave && currentRelpath) {
    console.log(`💾 [Layout] Saving layout preference: ${mode} for ${currentPlaylistType} playlist: ${currentRelpath}`);
    await savePlaylistLayout(currentRelpath, mode, currentPlaylistType);
  }
}

/**
 * Cycles through layout modes
 */
export async function cycleLayoutMode() {
  const modes = Object.values(LAYOUT_MODES);
  const currentIndex = modes.indexOf(currentLayoutMode);
  const nextIndex = (currentIndex + 1) % modes.length;
  const nextMode = modes[nextIndex];
  
  console.log(`🔄 [Layout] Cycling from ${currentLayoutMode} to ${nextMode}`);
  await applyLayoutMode(nextMode);
}

/**
 * Gets current layout mode
 * @returns {string} Current layout mode
 */
export function getCurrentLayoutMode() {
  return currentLayoutMode;
}

/**
 * Sets up layout toggle button
 */
export function setupLayoutToggleButton() {
  const toggleLayoutBtn = document.getElementById('toggleLayoutBtn');
  
  if (!toggleLayoutBtn) {
    console.warn('⚠️ [Layout] Toggle layout button not found');
    return;
  }
  
  toggleLayoutBtn.addEventListener('click', function() {
    cycleLayoutMode();
  });
  
  console.log('✅ [Layout] Layout toggle button initialized');
}

/**
 * Initialize playlist layout manager
 * @param {Object} config - Configuration object
 * @param {string} config.relpath - Relative path or virtual playlist identifier
 * @param {string} config.playlistType - 'regular' or 'virtual'
 */
export async function initializePlaylistLayoutManager(config = {}) {
  console.log('🎵 [Layout] Initializing playlist layout manager');
  
  // Store configuration
  currentRelpath = config.relpath || null;
  currentPlaylistType = config.playlistType || 'regular';
  
  // Load saved layout preference
  if (currentRelpath) {
    console.log(`🔍 [Layout] Loading layout preference for ${currentPlaylistType} playlist: ${currentRelpath}`);
    const savedLayout = await loadPlaylistLayout(currentRelpath, currentPlaylistType);
    currentLayoutMode = savedLayout;
    console.log(`🎵 [Layout] Loaded saved layout: ${savedLayout}`);
  }
  
  // Set up the toggle button
  setupLayoutToggleButton();
  
  // Apply initial layout (skip saving since this is loading saved preference)
  setTimeout(async () => {
    await applyLayoutMode(currentLayoutMode, true);
  }, 100);

  // Attach resize listener once for dynamic height in UNDER_VIDEO
  if (!resizeListenerAttached) {
    window.addEventListener('resize', () => {
      if (currentLayoutMode === LAYOUT_MODES.UNDER_VIDEO) {
        recalcUnderVideoMaxHeight();
      }
    });
    resizeListenerAttached = true;
  }
  
  // Add global functions for debugging
  window.setPlaylistLayout = async function(mode) {
    if (Object.values(LAYOUT_MODES).includes(mode)) {
      await applyLayoutMode(mode);
    } else {
      console.warn('⚠️ [Layout] Invalid mode. Use:', Object.values(LAYOUT_MODES));
    }
  };
  
  window.getPlaylistLayout = function() {
    return currentLayoutMode;
  };
  
  window.cyclePlaylistLayout = cycleLayoutMode;
  
  console.log('🎵 [Layout] Global functions available:');
  console.log('  - setPlaylistLayout(mode) - Set specific layout');
  console.log('  - getPlaylistLayout() - Get current layout');
  console.log('  - cyclePlaylistLayout() - Cycle to next layout');
} 