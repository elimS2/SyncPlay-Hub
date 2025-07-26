// Player state management functions extracted from player-utils.js

/**
 * Save volume to database with debouncing
 * @param {number} volume - volume level (0.0-1.0)
 * @param {Object} context - context for getting track data
 * @param {number} context.currentIndex - current track index
 * @param {Array} context.queue - track queue
 * @param {HTMLAudioElement} context.media - audio element
 * @param {Object} context.state - state object with volumeSaveTimeout and lastSavedVolume
 */
export async function saveVolumeToDatabase(volume, context) {
  clearTimeout(context.state.volumeSaveTimeout);
  context.state.volumeSaveTimeout = setTimeout(async () => {
    try {
      const currentTrack = context.currentIndex >= 0 && context.currentIndex < context.queue.length ? context.queue[context.currentIndex] : null;
      const payload = {
        volume: volume,
        volume_from: context.state.lastSavedVolume || 1.0,
        video_id: currentTrack ? currentTrack.video_id : 'system',
        position: context.media.currentTime || null,
        source: 'web'
      };
      
      await fetch('/api/volume/set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      console.log(`💾 Volume saved: ${Math.round((context.state.lastSavedVolume || 1.0) * 100)}% → ${Math.round(volume * 100)}%`);
      if (currentTrack) {
        console.log(`🎵 Track: ${currentTrack.name} at ${Math.round(context.media.currentTime)}s`);
      }
      
      context.state.lastSavedVolume = volume;
    } catch (error) {
      console.warn('⚠️ Failed to save volume:', error);
    }
  }, 500); // Debounce by 500ms to avoid excessive API calls
}

/**
 * Load saved volume from database
 * @param {HTMLAudioElement} media - audio element
 * @param {HTMLElement} cVol - volume control element
 * @param {Object} state - state object with lastSavedVolume
 * @param {Function} updateMuteIcon - function to update mute icon
 */
export async function loadSavedVolume(media, cVol, state, updateMuteIcon) {
  try {
    const response = await fetch('/api/volume/get');
    const data = await response.json();
    
    if (data.volume !== undefined) {
      media.volume = data.volume;
      cVol.value = data.volume;
      state.lastSavedVolume = data.volume; // Set initial saved volume
      console.log(`🔊 Loaded saved volume: ${data.volume_percent}%`);
    } else {
      // Default volume if no saved setting
      media.volume = 1.0;
      cVol.value = 1.0;
      state.lastSavedVolume = 1.0; // Set default as saved volume
      console.log('🔊 Using default volume: 100%');
    }
  } catch (error) {
    console.warn('⚠️ Failed to load saved volume, using default:', error);
    media.volume = 1.0;
    cVol.value = 1.0;
    state.lastSavedVolume = 1.0; // Set default as saved volume
  }
  
  updateMuteIcon();
}

/**
 * Synchronize player state with remote control API
 * @param {string} playerType - player type ('regular' or 'virtual')
 * @param {Object} context - context with currentIndex, queue, media
 */
export async function syncRemoteState(playerType = 'regular', context) {
    const ctx = context || window;
    const { currentIndex, queue, media } = ctx;
    
    try {
        const currentTrack = currentIndex >= 0 && currentIndex < queue.length ? queue[currentIndex] : null;
        
        // Get current like/dislike button states
        const likeButton = document.getElementById('cLike');
        const dislikeButton = document.getElementById('cDislike');
        const likeActive = likeButton ? likeButton.classList.contains('like-active') : false;
        const dislikeActive = dislikeButton ? dislikeButton.classList.contains('dislike-active') : false;
        
        const playerState = {
            current_track: currentTrack,
            playing: !media.paused && currentTrack !== null,
            volume: media.volume,
            progress: media.currentTime || 0,
            playlist: queue,
            current_index: currentIndex,
            last_update: Date.now() / 1000,
            player_type: playerType,
            player_source: window.location.pathname,
            like_active: likeActive,
            dislike_active: dislikeActive
        };
        
        console.log('🎮 Syncing remote state:', {
            track: currentTrack?.name || 'No track',
            playing: playerState.playing,
            progress: Math.floor(playerState.progress),
            index: currentIndex
        });
        
        // Update the global PLAYER_STATE via internal API call
        const response = await fetch('/api/remote/sync_internal', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(playerState)
        });
        
        if (!response.ok) {
            console.warn('Remote sync failed with status:', response.status);
        }
    } catch(err) {
        console.warn('Remote sync failed:', err);
    }
} 