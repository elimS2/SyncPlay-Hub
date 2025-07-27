/**
 * Track Order Manager
 * 
 * Manages track ordering modes: shuffle, smart shuffle, order by date
 */

import { loadPlaylistPreference, savePlaylistPreference } from './playlist-preferences.js';

// Order modes
export const ORDER_MODES = {
  SHUFFLE: 'shuffle',
  SMART_SHUFFLE: 'smart_shuffle', 
  ORDER_BY_DATE: 'order_by_date'
};

// Current order state
let currentOrderMode = null; // Will be set after loading saved preference

// Configuration object to store functions and data
let config = null;

/**
 * Applies the specified order mode
 * @param {string} mode - Order mode to apply
 * @param {boolean} skipSave - Skip saving preference (for initial load)
 */
export async function applyOrderMode(mode, skipSave = false) {
  if (!config) {
    console.warn('⚠️ [Order] Configuration not set');
    return;
  }

  const {
    tracks,
    shuffle,
    smartShuffle,
    orderByPublishDate,
    playIndex,
    updateCurrentTrackTitle,
    relpath,
    playlistType,
    getCurrentIndex,
    setQueue,
    showNotification
  } = config;

  let newQueue;
  let logMessage;
  let preferenceValue;

  switch (mode) {
    case ORDER_MODES.SHUFFLE:
      // Regular random shuffle
      newQueue = [...tracks];
      shuffle(newQueue);
      logMessage = '🔀 Random shuffle applied to all tracks';
      preferenceValue = 'shuffle';
      break;
      
    case ORDER_MODES.SMART_SHUFFLE:
      // Smart shuffle based on last play time
      newQueue = smartShuffle([...tracks]);
      logMessage = '🧠 Smart shuffle applied (grouped by last play time)';
      preferenceValue = 'smart';
      break;
      
    case ORDER_MODES.ORDER_BY_DATE:
      // Sort tracks by YouTube publish date (oldest first)
      newQueue = orderByPublishDate([...tracks]);
      logMessage = `📅 [${playlistType}] Tracks ordered by YouTube publish date (oldest first)`;
      preferenceValue = 'order_by_date';
      break;
      
    default:
      console.warn('⚠️ [Order] Unknown order mode:', mode);
      return;
  }

  // Apply the new queue
  setQueue(newQueue);
  console.log(logMessage);
  
  // Save preference (unless this is initial load)
  if (!skipSave) {
    console.log(`💾 [Order] Saving preference: ${preferenceValue} for ${playlistType} playlist: ${relpath}`);
    await savePlaylistPreference(relpath, preferenceValue, playlistType);
  }
  
  // Start playing from beginning (only if not initial load)
  if (!skipSave) {
    playIndex(0);
  }
  
  // Update track title after reordering
  const currentIndex = getCurrentIndex();
  if (currentIndex >= 0 && currentIndex < newQueue.length) {
    updateCurrentTrackTitle(newQueue[currentIndex]);
  }
  
  // Update button text
  updateOrderButtonText(mode);
  
  currentOrderMode = mode;
}

/**
 * Cycles through order modes
 */
export async function cycleOrderMode() {
  const modes = Object.values(ORDER_MODES);
  const currentIndex = modes.indexOf(currentOrderMode);
  const nextIndex = (currentIndex + 1) % modes.length;
  const nextMode = modes[nextIndex];
  
  console.log(`🔄 [Order] Cycling from ${currentOrderMode} to ${nextMode}`);
  await applyOrderMode(nextMode);
}

/**
 * Gets current order mode
 * @returns {string} Current order mode
 */
export function getCurrentOrderMode() {
  return currentOrderMode;
}

/**
 * Updates the order button text to show current mode
 * @param {string} mode - Current order mode
 */
function updateOrderButtonText(mode) {
  const orderBtn = document.getElementById('orderBtn');
  
  if (!orderBtn) {
    console.warn('⚠️ [Order] Order button not found');
    return;
  }

  const modeText = {
    [ORDER_MODES.SHUFFLE]: 'Order: Shuffle',
    [ORDER_MODES.SMART_SHUFFLE]: 'Order: Smart',
    [ORDER_MODES.ORDER_BY_DATE]: 'Order: Date'
  };
  
  orderBtn.querySelector('span:last-child').textContent = modeText[mode];
}

/**
 * Sets up order toggle button
 */
export function setupOrderToggleButton() {
  const orderBtn = document.getElementById('orderBtn');
  
  if (!orderBtn) {
    console.warn('⚠️ [Order] Order button not found');
    return;
  }
  
  orderBtn.addEventListener('click', function() {
    cycleOrderMode();
  });
  
  console.log('✅ [Order] Order toggle button initialized');
}

/**
 * Initialize track order manager
 * @param {Object} orderConfig - Configuration object with all necessary functions and data
 */
export async function initializeTrackOrderManager(orderConfig) {
  console.log('🎵 [Order] Initializing track order manager');
  
  // Store configuration
  config = orderConfig;
  
  // Load saved preference and set initial mode
  const { relpath, playlistType } = orderConfig;
  console.log(`🔍 [Order] Loading preference for ${playlistType} playlist: ${relpath}`);
  const savedPreference = await loadPlaylistPreference(relpath, playlistType);
  
  // Map saved preference to order mode
  switch (savedPreference) {
    case 'smart':
      currentOrderMode = ORDER_MODES.SMART_SHUFFLE;
      break;
    case 'order_by_date':
      currentOrderMode = ORDER_MODES.ORDER_BY_DATE;
      break;
    case 'shuffle':
    default:
      currentOrderMode = ORDER_MODES.SHUFFLE;
      break;
  }
  
  console.log(`🎵 [Order] Loaded saved preference: ${savedPreference} -> ${currentOrderMode}`);
  
  // Set up the toggle button
  setupOrderToggleButton();
  
  // Apply initial order mode (skip saving since this is loading saved preference)
  setTimeout(async () => {
    await applyOrderMode(currentOrderMode, true);
  }, 100);
  
  // Add global functions for debugging
  window.setTrackOrder = async function(mode) {
    if (Object.values(ORDER_MODES).includes(mode)) {
      await applyOrderMode(mode);
    } else {
      console.warn('⚠️ [Order] Invalid mode. Use:', Object.values(ORDER_MODES));
    }
  };
  
  window.getTrackOrder = function() {
    return currentOrderMode;
  };
  
  window.cycleTrackOrder = cycleOrderMode;
  
  console.log('🎵 [Order] Global functions available:');
  console.log('  - setTrackOrder(mode) - Set specific order mode');
  console.log('  - getTrackOrder() - Get current order mode');
  console.log('  - cycleTrackOrder() - Cycle to next order mode');
} 