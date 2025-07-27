// Playlist Preferences Module - Shared functionality for saving/loading playlist settings

/**
 * Save playlist display preference (shuffle, smart, order_by_date)
 * @param {string} relpath - Relative path or virtual playlist identifier
 * @param {string} preference - Preference to save
 * @param {string} playlistType - 'regular' or 'virtual'
 */
export async function savePlaylistPreference(relpath, preference, playlistType = 'regular') {
  if (!relpath) return;
  
  try {
    const response = await fetch('/api/save_display_preference', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        relpath: relpath,
        preference: preference
      })
    });
    
    const result = await response.json();
    if (result.status === 'ok') {
      console.log(`💾 ${playlistType} playlist preference saved: ${preference}`);
    } else {
      console.warn(`❌ Failed to save ${playlistType} playlist preference:`, result.message);
    }
  } catch (error) {
    console.error(`❌ Error saving ${playlistType} playlist preference:`, error);
  }
}

/**
 * Save playlist playback speed
 * @param {string} relpath - Relative path or virtual playlist identifier
 * @param {number} speed - Speed to save
 * @param {string} playlistType - 'regular' or 'virtual'
 */
export async function savePlaylistSpeed(relpath, speed, playlistType = 'regular') {
  if (!relpath) return;
  
  try {
    const response = await fetch('/api/save_playback_speed', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        relpath: relpath,
        speed: speed
      })
    });
    
    const result = await response.json();
    if (result.status === 'ok') {
      console.log(`⚡ ${playlistType} playlist speed saved: ${speed}x`);
    } else {
      console.warn(`❌ Failed to save ${playlistType} playlist speed:`, result.message);
    }
  } catch (error) {
    console.error(`❌ Error saving ${playlistType} playlist speed:`, error);
  }
}

/**
 * Load playlist playback speed
 * @param {string} relpath - Relative path or virtual playlist identifier
 * @param {string} playlistType - 'regular' or 'virtual'
 * @returns {Promise<number>} - Saved speed or default (1.0)
 */
export async function loadPlaylistSpeed(relpath, playlistType = 'regular') {
  if (!relpath) return 1.0; // Default fallback
  
  try {
    const response = await fetch(`/api/get_playback_speed?relpath=${encodeURIComponent(relpath)}`);
    const result = await response.json();
    
    if (result.status === 'ok') {
      console.log(`⚡ Loaded ${playlistType} playlist speed: ${result.speed}x`);
      return result.speed;
    } else {
      console.warn(`❌ Failed to load ${playlistType} playlist speed:`, result.message);
      return 1.0; // Default fallback
    }
  } catch (error) {
    console.error(`❌ Error loading ${playlistType} playlist speed:`, error);
    return 1.0; // Default fallback
  }
}

/**
 * Load playlist display preference
 * @param {string} relpath - Relative path or virtual playlist identifier
 * @param {string} playlistType - 'regular' or 'virtual'
 * @returns {Promise<string>} - Saved preference or default
 */
export async function loadPlaylistPreference(relpath, playlistType = 'regular') {
  if (!relpath) {
    // Return appropriate default based on playlist type
    return playlistType === 'virtual' ? 'smart' : 'shuffle';
  }
  
  try {
    const response = await fetch(`/api/get_display_preference?relpath=${encodeURIComponent(relpath)}`);
    const result = await response.json();
    
    if (result.status === 'ok') {
      console.log(`📂 Loaded ${playlistType} playlist preference: ${result.preference}`);
      return result.preference;
    } else {
      console.warn(`❌ Failed to load ${playlistType} playlist preference:`, result.message);
      return playlistType === 'virtual' ? 'smart' : 'shuffle'; // Default fallback
    }
  } catch (error) {
    console.error(`❌ Error loading ${playlistType} playlist preference:`, error);
    return playlistType === 'virtual' ? 'smart' : 'shuffle'; // Default fallback
  }
}

/**
 * Apply display preference to queue
 * @param {Array} tracks - Original tracks array
 * @param {string} preference - Preference to apply
 * @param {Function} shuffle - Shuffle function
 * @param {Function} smartShuffle - Smart shuffle function
 * @param {Function} orderByPublishDate - Order by date function
 * @returns {Array} - New queue with applied preference
 */
export function applyDisplayPreference(tracks, preference, shuffle, smartShuffle, orderByPublishDate) {
  let queue = [];
  
  switch (preference) {
    case 'smart':
      queue = smartShuffle([...tracks]);
      console.log('🧠 Applied smart shuffle from saved preference (grouped by last play time)');
      break;
    case 'order_by_date':
      queue = orderByPublishDate([...tracks]);
      console.log('📅 Applied order by date from saved preference');
      break;
    case 'shuffle':
    default:
      queue = [...tracks];
      shuffle(queue);
      console.log('🔀 Applied random shuffle from saved preference');
      break;
  }
  
  return queue;
}

/**
 * Initialize playlist preferences and apply saved settings
 * @param {Object} config - Configuration object
 * @param {string} config.relpath - Relative path or virtual playlist identifier
 * @param {string} config.playlistType - 'regular' or 'virtual'
 * @param {Array} config.tracks - Original tracks array
 * @param {Array} config.speedOptions - Available speed options
 * @param {Function} config.shuffle - Shuffle function
 * @param {Function} config.smartShuffle - Smart shuffle function
 * @param {Function} config.orderByPublishDate - Order by date function
 * @returns {Promise<Object>} - Object with queue and currentSpeedIndex
 */
export async function initializePlaylistPreferences(config) {
  const {
    relpath,
    playlistType,
    tracks,
    speedOptions,
    shuffle,
    smartShuffle,
    orderByPublishDate
  } = config;
  
  // Load saved preference and apply it
  const savedPreference = await loadPlaylistPreference(relpath, playlistType);
  let queue = applyDisplayPreference(tracks, savedPreference, shuffle, smartShuffle, orderByPublishDate);
  
  // Load and apply saved playback speed
  const savedSpeed = await loadPlaylistSpeed(relpath, playlistType);
  const speedIndex = speedOptions.indexOf(savedSpeed);
  let currentSpeedIndex = 2; // Default to 1x (index 2)
  
  if (speedIndex !== -1) {
    currentSpeedIndex = speedIndex;
    console.log(`⚡ Applied saved speed: ${savedSpeed}x`);
  } else {
    console.warn(`⚠️ Invalid saved speed ${savedSpeed}x, using default 1x`);
  }
  
  return { queue, currentSpeedIndex };
}

/**
 * Re-setup handlers with updated queue after sorting
 * @param {Array} newQueue - New queue after sorting
 * @param {Array} tracks - Original tracks array
 * @param {Function} getCurrentIndex - Function to get current index
 * @param {Function} playIndex - Function to play track at index
 * @param {string} playlistType - 'regular' or 'virtual'
 * @param {Function} showNotification - Function to show notifications
 */
async function reSetupHandlers(newQueue, tracks, getCurrentIndex, playIndex, playlistType, showNotification) {
  // Re-setup like/dislike handlers with updated queue
  const cLike = document.getElementById('cLike');
  const cDislike = document.getElementById('cDislike');
  if (cLike && cDislike) {
    // Import the function dynamically to avoid circular dependencies
    import('/static/js/modules/controls.js').then(({ setupLikeDislikeHandlers }) => {
      setupLikeDislikeHandlers(cLike, cDislike, {
        currentIndex: getCurrentIndex,
        queue: newQueue,
        media: document.getElementById('player'),
        reportEvent: (videoId, event, position) => {
          // Simple reportEvent implementation
          fetch('/api/event', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_id: videoId, event, position })
          }).catch(console.error);
        },
        likedCurrent: false
      });
    });
  }
  
  // Re-setup delete current button handler with updated queue
  const deleteCurrentBtn = document.getElementById('deleteCurrentBtn');
  if (deleteCurrentBtn) {
    import('/static/js/modules/controls.js').then(({ setupDeleteCurrentHandler }) => {
      setupDeleteCurrentHandler(deleteCurrentBtn, {
        currentIndex: getCurrentIndex,
        queue: newQueue,
        tracks: tracks, // Use original tracks array
        media: document.getElementById('player'),
        playIndex: playIndex,
        renderList: () => {
          // Re-render list with updated queue
          const listElem = document.getElementById('playlist');
          if (listElem) {
            listElem.innerHTML = '';
            newQueue.forEach((t, idx) => {
              // Create list item (simplified version)
              const li = document.createElement('li');
              li.textContent = t.name;
              listElem.appendChild(li);
            });
          }
        },
        showNotification: showNotification,
        loadTrack: (idx, autoplay) => {
          if (idx >= 0 && idx < newQueue.length) {
            playIndex(idx);
          }
        },
        getCurrentIndex: getCurrentIndex,
        setCurrentIndex: (newIdx) => {
          // This will be handled by the calling context
          console.log(`Setting current index to ${newIdx}`);
        }
      }, playlistType);
    });
    
    // Update delete button tooltip after re-setup
    if (deleteCurrentBtn && deleteCurrentBtn.updateTooltip) {
      deleteCurrentBtn.updateTooltip();
    }
  }
  
  // Re-setup YouTube button handler with updated queue
  const cYoutube = document.getElementById('cYoutube');
  if (cYoutube) {
    import('/static/js/modules/controls.js').then(({ setupYouTubeHandler }) => {
      setupYouTubeHandler(cYoutube, {
        currentIndex: getCurrentIndex,
        queue: newQueue
      });
    });
  }
}

/**
 * Setup sort button handlers to eliminate code duplication
 * @param {Object} config - Configuration object
 * @param {HTMLElement} config.shuffleBtn - Shuffle button element
 * @param {HTMLElement} config.smartShuffleBtn - Smart shuffle button element
 * @param {HTMLElement} config.orderByDateBtn - Order by date button element
 * @param {Array} config.tracks - Original tracks array
 * @param {Function} config.shuffle - Shuffle function
 * @param {Function} config.smartShuffle - Smart shuffle function
 * @param {Function} config.orderByPublishDate - Order by date function
 * @param {Function} config.savePlaylistPreference - Function to save preference
 * @param {Function} config.playIndex - Function to play track at index
 * @param {Function} config.updateCurrentTrackTitle - Function to update track title
 * @param {string} config.relpath - Relative path or virtual playlist identifier
 * @param {string} config.playlistType - 'regular' or 'virtual'
 * @param {Function} config.getCurrentIndex - Function to get current index
 * @param {Function} config.getQueue - Function to get current queue
 * @param {Function} config.setQueue - Function to set new queue
 * @param {Function} config.showNotification - Function to show notifications
 */
export function setupSortButtonHandlers(config) {
  const {
    shuffleBtn,
    smartShuffleBtn,
    orderByDateBtn,
    tracks,
    shuffle,
    smartShuffle,
    orderByPublishDate,
    savePlaylistPreference,
    playIndex,
    updateCurrentTrackTitle,
    relpath,
    playlistType,
    getCurrentIndex,
    getQueue,
    setQueue,
    showNotification
  } = config;

  // Shuffle button handler
  if (shuffleBtn) {
    shuffleBtn.onclick = async () => {
      // Regular random shuffle
      const newQueue = [...tracks];
      shuffle(newQueue);
      setQueue(newQueue);
      console.log('🔀 Random shuffle applied to all tracks');
      
      // Save preference
      await savePlaylistPreference(relpath, 'shuffle', playlistType);
      
      playIndex(0);
      // Update track title after shuffle
      const currentIndex = getCurrentIndex();
      if (currentIndex >= 0 && currentIndex < newQueue.length) {
        updateCurrentTrackTitle(newQueue[currentIndex]);
      }
      
      // Re-setup handlers with updated queue
      await reSetupHandlers(newQueue, tracks, getCurrentIndex, playIndex, playlistType, showNotification);
    };
  }

  // Smart shuffle button handler
  if (smartShuffleBtn) {
    smartShuffleBtn.onclick = async () => {
      // Smart shuffle based on last play time
      const newQueue = smartShuffle([...tracks]);
      setQueue(newQueue);
      console.log('🧠 Smart shuffle applied (grouped by last play time)');
      
      // Save preference
      await savePlaylistPreference(relpath, 'smart', playlistType);
      
      playIndex(0);
      // Update track title after smart shuffle
      const currentIndex = getCurrentIndex();
      if (currentIndex >= 0 && currentIndex < newQueue.length) {
        updateCurrentTrackTitle(newQueue[currentIndex]);
      }
      
      // Re-setup handlers with updated queue
      await reSetupHandlers(newQueue, tracks, getCurrentIndex, playIndex, playlistType, showNotification);
    };
  }

  // Order by date button handler
  if (orderByDateBtn) {
    orderByDateBtn.onclick = async () => {
      // Sort tracks by YouTube publish date (oldest first)
      const newQueue = orderByPublishDate([...tracks]);
      setQueue(newQueue);
      console.log(`📅 [${playlistType}] Tracks ordered by YouTube publish date (oldest first)`);
      
      // Save preference
      await savePlaylistPreference(relpath, 'order_by_date', playlistType);
      
      playIndex(0);
      // Update track title after ordering
      const currentIndex = getCurrentIndex();
      if (currentIndex >= 0 && currentIndex < newQueue.length) {
        updateCurrentTrackTitle(newQueue[currentIndex]);
      }
      
      // Re-setup handlers with updated queue
      await reSetupHandlers(newQueue, tracks, getCurrentIndex, playIndex, playlistType, showNotification);
    };
  }
}

export default {
  savePlaylistPreference,
  savePlaylistSpeed,
  loadPlaylistSpeed,
  loadPlaylistPreference,
  applyDisplayPreference,
  initializePlaylistPreferences,
  setupSortButtonHandlers
}; 