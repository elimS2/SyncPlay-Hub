// Playback control functions extracted from player-utils.js

/**
 * Execute track deletion without confirmation - used by delete handlers
 * @param {Object} context - execution context
 * @param {string} playerType - player type for logging ('regular' or 'virtual')
 */
export async function executeDeleteWithoutConfirmation(context, playerType = 'regular') {
    // Get current index value (handle both direct values and functions)
    const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
    
    // Check if there's a current track
    if (currentIndex < 0 || currentIndex >= context.queue.length) {
        context.showNotification('❌ No active track to delete', 'error');
        return;
    }
    
    const currentTrack = context.queue[currentIndex];
    
    console.log(`🗑️ Deleting current track (remote command): ${currentTrack.name} (${currentTrack.video_id})`);
    
    try {
        // CRITICAL: First pause and clear media source to release file lock
        context.media.pause();
        const currentTime = context.media.currentTime; // Save position for potential restore
        context.media.src = ''; // This releases the file lock
        context.media.load(); // Ensure the media element is properly reset
        
        console.log('🔓 Media file released, proceeding with deletion...');
        
        // Give a small delay to ensure file is fully released
        await new Promise(resolve => setTimeout(resolve, 200));
        
        // Send delete request to API
        const response = await fetch('/api/channels/delete_track', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                video_id: currentTrack.video_id
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'ok') {
            const successMessage = playerType === 'regular' ? 
                `✅ Current track deleted successfully: ${result.message}` : 
                `✅ Track deleted successfully: ${result.message}`;
            console.log(successMessage);
            
            // Remove track from current queue
            context.queue.splice(currentIndex, 1);
            
            // Also remove from original tracks array
            const originalIndex = context.tracks.findIndex(t => t.video_id === currentTrack.video_id);
            if (originalIndex !== -1) {
                context.tracks.splice(originalIndex, 1);
            }
            
            // Handle playback continuation
            if (context.queue.length > 0) {
                // Stay at the same index if possible, or go to first track
                const nextIndex = currentIndex < context.queue.length ? currentIndex : 0;
                console.log(`🎵 Auto-continuing to next track at index ${nextIndex}`);
                context.playIndex(nextIndex);
            } else {
                // No tracks left - note: cannot modify currentIndex directly as it might be a function result
                context.showNotification('📭 Playlist is empty - all tracks deleted', 'info');
            }
            
            // Update the list display
            context.renderList();
            
            // Show success message
            context.showNotification(`✅ Track deleted: ${result.message}`, 'success');
            
        } else {
            const errorType = playerType === 'regular' ? 'current track' : 'track';
            console.error(`❌ Failed to delete ${errorType}:`, result.error);
            context.showNotification(`❌ Deletion error: ${result.error}`, 'error');
            
            // On failure, try to restore playback of the same track
            console.log('🔄 Attempting to restore playback after deletion failure...');
            try {
                context.loadTrack(currentIndex, true);
                if (currentTime && isFinite(currentTime)) {
                    setTimeout(() => {
                        context.media.currentTime = currentTime; // Restore position
                    }, 500);
                }
            } catch (restoreError) {
                console.warn('⚠️ Could not restore playback:', restoreError);
            }
        }
        
    } catch (error) {
        const errorType = playerType === 'regular' ? 'current track' : 'track';
        console.error(`❌ Error deleting ${errorType}:`, error);
        context.showNotification(`❌ Network error: ${error.message}`, 'error');
        
        // On error, try to restore playback
        console.log('🔄 Attempting to restore playback after network error...');
        try {
            context.loadTrack(currentIndex, true);
            if (currentTime && isFinite(currentTime)) {
                setTimeout(() => {
                    context.media.currentTime = currentTime; // Restore position
                }, 500);
            }
        } catch (restoreError) {
            console.warn('⚠️ Could not restore playback:', restoreError);
        }
    }
}

/**
 * Handle mouse wheel for volume control
 * @param {Event} e - mouse wheel event
 * @param {HTMLElement} cVol - volume control element
 * @param {HTMLMediaElement} media - media element
 * @param {Function} updateMuteIcon - function to update mute icon
 * @param {Function} saveVolumeToDatabase - function to save volume to database
 * @param {Object} volumeState - volume state object
 */
export function handleVolumeWheel(e, cVol, media, updateMuteIcon, saveVolumeToDatabase, volumeState) {
  e.preventDefault(); // Prevent page scroll
  e.stopPropagation(); // Stop event bubbling
  
  // Block remote volume commands while user is using wheel
  volumeState.isVolumeWheelActive = true;
  clearTimeout(volumeState.volumeWheelTimeout);
  volumeState.volumeWheelTimeout = setTimeout(() => {
    volumeState.isVolumeWheelActive = false;
  }, 2000); // 2 second cooldown
  
  const currentVolume = parseFloat(cVol.value);
  const step = 0.01; // 1% step
  
  let newVolume;
  if (e.deltaY < 0) {
    // Wheel up - increase volume
    newVolume = Math.min(1.0, currentVolume + step);
  } else {
    // Wheel down - decrease volume
    newVolume = Math.max(0.0, currentVolume - step);
  }
  
  // Check if we have an actual change
  if (Math.abs(newVolume - currentVolume) < 0.001) {
    return;
  }
  
  // Update slider and media volume
  cVol.value = newVolume;
  media.volume = newVolume;
  media.muted = media.volume === 0;
  updateMuteIcon();
  
  // Force visual update
  cVol.dispatchEvent(new Event('input', { bubbles: true }));
  
  saveVolumeToDatabase(media.volume);
  
  console.log(`🎚️ Volume wheel control: ${Math.round(currentVolume * 100)}% → ${Math.round(newVolume * 100)}%`);
}

/**
 * Stop stream synchronization timer
 * @param {number|null} tickTimer - timer ID to stop
 * @returns {null} - returns null to update tickTimer
 */
export function stopTick(tickTimer) {
  if (tickTimer) {
    clearInterval(tickTimer);
    return null;
  }
  return tickTimer;
}

/**
 * Stop playback and reset position
 * @param {HTMLAudioElement} media - audio element
 */
export function stopPlayback(media) {
  media.pause();
  media.currentTime = 0;
}

/**
 * Start playback of track by index
 * @param {number} idx - track index to play
 * @param {Function} loadTrack - function to load track
 */
export function playIndex(idx, loadTrack) {
  loadTrack(idx, true);
}

/**
 * Update mute icon based on media state
 * @param {HTMLAudioElement} media - audio element
 * @param {HTMLElement} cMute - mute button element
 */
export function updateMuteIcon(media, cMute) {
  if (media.muted || media.volume === 0) {
    cMute.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg>';
  } else {
    cMute.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/></svg>';
  }
}

/**
 * Go to next track in queue
 * @param {number} currentIndex - current track index
 * @param {Array} queue - track queue
 * @param {Function} reportEvent - event reporting function
 * @param {Function} playIndex - play by index function
 * @param {Function} sendStreamEvent - stream event function
 * @param {HTMLAudioElement} media - audio element
 */
export function nextTrack(currentIndex, queue, reportEvent, playIndex, sendStreamEvent, media) {
  if (currentIndex + 1 < queue.length) {
    // send event for current track before switching
    if(currentIndex>=0){ reportEvent(queue[currentIndex].video_id,'next'); }
    playIndex(currentIndex + 1);
    sendStreamEvent({action:'next', idx: currentIndex, paused: media.paused, position:0});
  }
}

/**
 * Go to previous track in queue
 * @param {number} currentIndex - current track index
 * @param {Array} queue - track queue
 * @param {Function} reportEvent - event reporting function
 * @param {Function} playIndex - play by index function
 * @param {Function} sendStreamEvent - stream event function
 * @param {HTMLAudioElement} media - audio element
 */
export function prevTrack(currentIndex, queue, reportEvent, playIndex, sendStreamEvent, media) {
  if (currentIndex - 1 >= 0) {
    if(currentIndex>=0){ reportEvent(queue[currentIndex].video_id,'prev'); }
    playIndex(currentIndex - 1);
    sendStreamEvent({action:'prev', idx: currentIndex, paused: media.paused, position: media.currentTime});
  }
}

/**
 * Start stream synchronization timer
 * @param {number|null} tickTimer - current timer ID
 * @param {string|null} streamIdLeader - stream leader ID
 * @param {Function} sendStreamEventFn - stream event function
 * @param {number} currentIndex - current track index
 * @param {HTMLAudioElement} media - audio element
 * @returns {number|null} - new timer ID or null
 */
export function startTick(tickTimer, streamIdLeader, sendStreamEventFn, currentIndex, media) {
  if(tickTimer||!streamIdLeader) return tickTimer;
  
  const newTickTimer = setInterval(()=>{
     if(!streamIdLeader) return;
     sendStreamEventFn({action:'tick', idx: currentIndex, position: media.currentTime, paused: media.paused});
  },1500);
  
  return newTickTimer;
}

/**
 * Perform keyboard seek in media element
 * @param {number} offsetSeconds - offset in seconds (can be negative)
 * @param {Object} context - context with necessary variables
 * @param {number} context.currentIndex - current track index
 * @param {Array} context.queue - track queue
 * @param {HTMLMediaElement} context.media - media element
 * @param {Function} context.recordSeekEvent - function to record seek event
 */
export function performKeyboardSeek(offsetSeconds, context) {
  const { currentIndex, queue, media, recordSeekEvent } = context;
  
  if (currentIndex < 0 || currentIndex >= queue.length || !media.duration) return;
  
  const seekFrom = media.currentTime;
  const seekTo = Math.max(0, Math.min(media.duration, seekFrom + offsetSeconds));
  
  if (Math.abs(seekTo - seekFrom) >= 1.0) {
    media.currentTime = seekTo;
    const track = queue[currentIndex];
    recordSeekEvent(track.video_id, seekFrom, seekTo, 'keyboard');
  }
}

/**
 * Sync like buttons state with remote state
 */
export async function syncLikeButtonsWithRemote() {
  try {
    const response = await fetch('/api/remote/status');
    if (response.ok) {
      const status = await response.json();
      
      const likeButton = document.getElementById('cLike');
      const dislikeButton = document.getElementById('cDislike');
      
      if (likeButton && status.like_active !== undefined) {
        if (status.like_active) {
          likeButton.classList.add('like-active');
        } else {
          likeButton.classList.remove('like-active');
        }
      }
      
      if (dislikeButton && status.dislike_active !== undefined) {
        if (status.dislike_active) {
          dislikeButton.classList.add('dislike-active');
        } else {
          dislikeButton.classList.remove('dislike-active');
        }
      }
    }
  } catch (error) {
    console.warn('Failed to sync like buttons with remote:', error);
  }
}

/**
 * Sync likes after user actions
 * @param {string} video_id - video ID
 * @param {string} action - action ('like' or 'dislike')
 * @param {Function} syncRemoteState - remote state sync function
 */
export async function syncLikesAfterAction(video_id, action, syncRemoteState) {
  console.log(`🎵 [Like Sync] Syncing likes after ${action} for ${video_id}`);
  
  // Just sync remote state to update remote control
  setTimeout(async () => {
    await syncRemoteState();
  }, 200);
}

/**
 * Setup like sync handlers for buttons
 * @param {Object} context - context with necessary data
 * @param {number} context.currentIndex - current track index
 * @param {Array} context.queue - track queue
 * @param {Function} context.syncLikesAfterAction - like sync function
 */
export function setupLikeSyncHandlers(context) {
  const { currentIndex, queue, syncLikesAfterAction } = context;
  
  const likeButton = document.getElementById('cLike');
  const dislikeButton = document.getElementById('cDislike');
  
  if (likeButton) {
    // Store original handler
    const originalLikeHandler = likeButton.onclick;
    
    likeButton.onclick = async function(e) {
      // Call original handler
      if (originalLikeHandler) {
        originalLikeHandler.call(this, e);
      }
      
      // Sync likes after action
      const currentTrack = currentIndex >= 0 && currentIndex < queue.length ? queue[currentIndex] : null;
      if (currentTrack && currentTrack.video_id) {
        await syncLikesAfterAction(currentTrack.video_id, 'like');
      }
    };
  }
  
  if (dislikeButton) {
    // Store original handler
    const originalDislikeHandler = dislikeButton.onclick;
    
    dislikeButton.onclick = async function(e) {
      // Call original handler
      if (originalDislikeHandler) {
        originalDislikeHandler.call(this, e);
      }
      
      // Sync likes after action
      const currentTrack = currentIndex >= 0 && currentIndex < queue.length ? queue[currentIndex] : null;
      if (currentTrack && currentTrack.video_id) {
        await syncLikesAfterAction(currentTrack.video_id, 'dislike');
      }
    };
  }
}

/**
 * Toggle playback (pause/play)
 * Automatically synchronizes with streaming API and starts ticker
 * @param {Object} context - context with media, sendStreamEvent, startTick
 */
export function togglePlayback(context) {
    const { media, sendStreamEvent, startTick } = context || window;
    
    if (media.paused) {
        media.play();
        sendStreamEvent({action:'play', position: media.currentTime, paused:false});
        startTick();
    } else {
        media.pause();
        sendStreamEvent({action:'pause', position: media.currentTime, paused:true});
    }
}

/**
 * Cycle through playback speeds cyclically
 * @param {Object} context - context with currentSpeedIndex, speedOptions, media, updateSpeedDisplay, reportEvent
 * @param {Function} savePlaylistSpeed - function to save speed to playlist settings (optional)
 * @param {string} playerType - player type for logging ('regular' or 'virtual')
 */
export async function cyclePlaybackSpeed(context, savePlaylistSpeed = null, playerType = 'regular') {
    const { currentSpeedIndex, speedOptions, media, updateSpeedDisplay, reportEvent, currentIndex, queue } = context;
    
    // Increment speed index cyclically
    const newSpeedIndex = (currentSpeedIndex + 1) % speedOptions.length;
    const newSpeed = speedOptions[newSpeedIndex];
    
    if (media) {
        media.playbackRate = newSpeed;
    }
    
    // Update display with new speed index - need to check if updateSpeedDisplay expects parameters
    if (updateSpeedDisplay.length > 0) {
        // Function expects parameters - call with correct new index
        const speedLabel = document.getElementById('speedLabel');
        const cSpeed = document.getElementById('cSpeed');
        updateSpeedDisplay(newSpeedIndex, speedOptions, speedLabel, cSpeed);
    } else {
        // Function is a wrapper - caller must update currentSpeedIndex first
        updateSpeedDisplay();
    }
    
    const logPrefix = playerType === 'virtual' ? '⏩ [Virtual]' : '⏩';
    console.log(`${logPrefix} Playback speed changed to ${newSpeed}x`);
    
    // Save the new speed to playlist settings (if provided)
    if (savePlaylistSpeed) {
        await savePlaylistSpeed(newSpeed);
    }
    
    // Report speed change event if we have a current track
    if (currentIndex >= 0 && currentIndex < queue.length) {
        const track = queue[currentIndex];
        reportEvent(track.video_id, 'speed_change', media.currentTime, { speed: newSpeed });
    }
    
    return newSpeedIndex; // Return new index for updating caller's state
}

/**
 * Delete track from playlist with file lock release
 * @param {Object} track - track to delete
 * @param {number} trackIndex - track index in queue
 * @param {Object} context - execution context
 */
export async function deleteTrack(track, trackIndex, context) {
    const { 
        queue, tracks, currentIndex, media, playIndex, renderList, 
        showNotification, loadTrack 
    } = context;
    
    try {
        // Confirm deletion
        const confirmMessage = `Delete track "${track.name.replace(/\s*\[.*?\]$/, '')}" from playlist?\n\nTrack will be moved to trash and can be restored.`;
        if (!confirm(confirmMessage)) {
            return;
        }
        
        console.log(`🗑️ Deleting track: ${track.name} (${track.video_id})`);
        
        // CRITICAL: File lock release logic (used always for reliability)
        let wasCurrentTrack = false;
        let currentTime = 0;
        
        if (trackIndex === currentIndex && !media.paused) {
            wasCurrentTrack = true;
            console.log('🔓 Deleting currently playing track - releasing file lock...');
            
            // Pause and clear media source to release file lock
            media.pause();
            currentTime = media.currentTime; // Save position for potential restore
            media.src = ''; // This releases the file lock
            media.load(); // Ensure the media element is properly reset
            
            console.log('🔓 Media file released, proceeding with deletion...');
            
            // Give a small delay to ensure file is fully released
            await new Promise(resolve => setTimeout(resolve, 200));
        }
        
        // Send delete request to API
        const response = await fetch('/api/channels/delete_track', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                video_id: track.video_id
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'ok') {
            console.log(`✅ Track deleted successfully: ${result.message}`);
            
            // Remove track from current queue
            queue.splice(trackIndex, 1);
            
            // Also remove from original tracks array
            const originalIndex = tracks.findIndex(t => t.video_id === track.video_id);
            if (originalIndex !== -1) {
                tracks.splice(originalIndex, 1);
            }
            
            // Adjust current index if needed
            const currentIdx = context.getCurrentIndex ? context.getCurrentIndex() : context.currentIndex;
            if (trackIndex < currentIdx) {
                // Track deleted before current position - shift current index back
                if (context.setCurrentIndex) {
                    context.setCurrentIndex(currentIdx - 1);
                } else {
                    context.currentIndex--;
                }
            } else if (trackIndex === currentIdx) {
                // If we deleted the currently playing track
                if (queue.length > 0) {
                    // Play the next track or the first one if we were at the end
                    const nextIndex = trackIndex < queue.length ? trackIndex : 0;
                    playIndex(nextIndex);
                } else {
                    // No tracks left - universal logic
                    media.pause();
                    media.src = '';
                    if (context.setCurrentIndex) {
                        context.setCurrentIndex(-1);
                    } else {
                        context.currentIndex = -1;
                    }
                    showNotification('📭 Playlist is empty - all tracks deleted', 'info');
                }
            }
            
            // Update the list display
            renderList();
            
            // Show success message
            showNotification(`✅ Track deleted: ${result.message}`, 'success');
            
        } else {
            console.error('❌ Failed to delete track:', result.error);
            showNotification(`❌ Deletion error: ${result.error}`, 'error');
            
            // On failure, try to restore playback if it was the current track (universal logic)
            if (wasCurrentTrack) {
                console.log('🔄 Attempting to restore playback after deletion failure...');
                try {
                    loadTrack(currentIndex, true);
                    if (currentTime && isFinite(currentTime)) {
                        setTimeout(() => {
                            media.currentTime = currentTime; // Restore position
                        }, 500);
                    }
                } catch (restoreError) {
                    console.warn('⚠️ Could not restore playback:', restoreError);
                }
            }
        }
        
    } catch (error) {
        console.error('❌ Error deleting track:', error);
        showNotification(`❌ Network error: ${error.message}`, 'error');
        
        // On error, try to restore playback (universal logic)
        if (wasCurrentTrack && trackIndex === context.currentIndex) {
            console.log('🔄 Attempting to restore playback after network error...');
            try {
                loadTrack(context.currentIndex, true);
                if (currentTime && isFinite(currentTime)) {
                    setTimeout(() => {
                        media.currentTime = currentTime; // Restore position
                    }, 500);
                }
            } catch (restoreError) {
                console.warn('⚠️ Could not restore playback:', restoreError);
            }
        }
    }
}

/**
 * Initialize Google Cast integration
 * @param {Object} context - execution context
 * @param {number} context.currentIndex - current track index
 * @param {Array} context.queue - track queue
 * @param {Function} context.castLoad - function to load track on Cast device
 * @returns {Object} - returns castContext and pendingCastTrack objects for external usage
 */
export function initializeGoogleCastIntegration(context) {
    const { currentIndex, queue, castLoad } = context;
    
    console.log('🔄 CAST DEBUG: Starting Google Cast integration setup...');
    
    let castContext = null;
    let pendingCastTrack = null;

    // Step 1: Check if Cast button element exists in DOM
    console.log('🔍 CAST DEBUG: Step 1 - Looking for Cast button element...');
    const castBtn = document.getElementById('castBtn');
    if(castBtn){
        console.log('✅ CAST DEBUG: Cast button element found!', castBtn);
        castBtn.style.display='inline-flex';
        console.log('✅ CAST DEBUG: Cast button made visible with display: inline-flex');
        
        // Add click handler for cast button
        castBtn.onclick = () => {
            console.log('🔘 CAST DEBUG: Cast button clicked!');
            if(!castContext) {
                console.warn('❌ CAST DEBUG: Cast context not available when button clicked');
                return;
            }
            
            console.log('🔄 CAST DEBUG: Checking current cast session...');
            const currentSession = castContext.getCurrentSession();
            if(currentSession) {
                console.log('🛑 CAST DEBUG: Active session found, ending it...');
                currentSession.endSession(false);
                console.log('✅ CAST DEBUG: Cast session ended');
            } else {
                console.log('🚀 CAST DEBUG: No active session, requesting new session...');
                castContext.requestSession().then(() => {
                    console.log('✅ CAST DEBUG: Cast session started successfully!');
                    // Load current track if available
                    if(currentIndex >= 0 && currentIndex < queue.length) {
                        console.log('🎵 CAST DEBUG: Loading current track to cast device...');
                        castLoad(queue[currentIndex]);
                    } else {
                        console.log('ℹ️ CAST DEBUG: No current track to load');
                    }
                }).catch(err => {
                    console.warn('❌ CAST DEBUG: Cast session failed:', err);
                });
            }
        };
        console.log('✅ CAST DEBUG: Click handler attached to Cast button');
    }else{
        console.error('❌ CAST DEBUG: Cast button element NOT FOUND in DOM!');
        console.log('🔍 CAST DEBUG: Available button elements:', 
            Array.from(document.querySelectorAll('button')).map(btn => btn.id || btn.className));
    }

    // Step 2: Set up Cast API callback
    console.log('🔄 CAST DEBUG: Step 2 - Setting up Cast API availability callback...');
    window.__onGCastApiAvailable = function(isAvailable){
        console.log('📡 CAST DEBUG: Cast API callback triggered, isAvailable=', isAvailable);
        
        if(isAvailable){
            console.log('✅ CAST DEBUG: Cast API is available, initializing...');
            try {
                console.log('🔄 CAST DEBUG: Getting Cast context instance...');
                castContext = cast.framework.CastContext.getInstance();
                console.log('✅ CAST DEBUG: Cast context obtained:', castContext);
                
                console.log('🔄 CAST DEBUG: Setting Cast context options...');
                castContext.setOptions({
                    receiverApplicationId: chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
                    autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED
                });
                console.log('✅ CAST DEBUG: Cast context options set successfully');
                
                // Double-check button visibility after API load
                const castBtn = document.getElementById('castBtn');
                if(castBtn){
                    castBtn.style.display='inline-flex';
                    castBtn.style.visibility='visible';
                    console.log('✅ CAST DEBUG: Cast button double-checked and made visible after API load');
                    console.log('🎯 CAST DEBUG: Cast button final styles:', {
                        display: castBtn.style.display,
                        visibility: castBtn.style.visibility,
                        offsetWidth: castBtn.offsetWidth,
                        offsetHeight: castBtn.offsetHeight
                    });
                }else{
                    console.error('❌ CAST DEBUG: Cast button element NOT FOUND after API load!');
                }
                
                // Set up session state change listener
                console.log('🔄 CAST DEBUG: Setting up session state change listener...');
                castContext.addEventListener(cast.framework.CastContextEventType.SESSION_STATE_CHANGED, (e) => {
                    console.log('🔄 CAST DEBUG: Session state changed:', e.sessionState);
                    if((e.sessionState === cast.framework.SessionState.SESSION_STARTED || 
                        e.sessionState === cast.framework.SessionState.SESSION_RESUMED) && pendingCastTrack){
                        console.log('🎵 CAST DEBUG: Loading pending track after session start...');
                        castLoad(pendingCastTrack);
                        pendingCastTrack = null;
                    }
                });
                console.log('✅ CAST DEBUG: Session state change listener attached');
                
                console.log('🎉 CAST DEBUG: Google Cast integration fully initialized!');
                
            } catch (error) {
                console.error('❌ CAST DEBUG: Error initializing Cast API:', error);
                console.error('❌ CAST DEBUG: Error stack:', error.stack);
            }
        } else {
            console.warn('❌ CAST DEBUG: Cast API is NOT available');
            console.log('ℹ️ CAST DEBUG: Possible reasons: no Cast devices, API blocked, network issues');
        }
    };
    
    console.log('✅ CAST DEBUG: Cast API callback function set up successfully');
    
    // Return the context objects for external usage
    return { castContext, pendingCastTrack, setCastContext: (ctx) => { castContext = ctx; }, setPendingCastTrack: (track) => { pendingCastTrack = track; } };
}

/**
 * Load track on Google Cast device
 * @param {Object} track - track to load
 * @param {Object} castState - cast state (castContext, setPendingCastTrack)
 */
export function castLoad(track, castState) {
    const { castContext, setPendingCastTrack } = castState;
    
    console.log('🎵 CAST DEBUG: castLoad() called for track:', track.name);
    
    if(!castContext) {
        console.warn('❌ CAST DEBUG: No cast context available for loading track');
        return;
    }
    
    console.log('🔄 CAST DEBUG: Getting current cast session...');
    const session = castContext.getCurrentSession();
    if(!session){
        console.log('📝 CAST DEBUG: No active session, saving track as pending');
        setPendingCastTrack(track);
        return;
    }
    
    console.log('✅ CAST DEBUG: Active cast session found, preparing media...');
    let absUrl = new URL(track.url, window.location.href).href;
    console.log('🔗 CAST DEBUG: Original URL:', track.url);
    console.log('🔗 CAST DEBUG: Absolute URL:', absUrl);
    
    // if hostname is localhost, replace with current local IP (taken from location)
    if (absUrl.includes('localhost')) {
        console.log('🔄 CAST DEBUG: Localhost detected, replacing with server IP...');
        if (typeof SERVER_IP !== 'undefined' && SERVER_IP) {
            absUrl = absUrl.replace('localhost', SERVER_IP);
            console.log('✅ CAST DEBUG: Replaced with SERVER_IP:', SERVER_IP);
        } else {
            absUrl = absUrl.replace('localhost', window.location.hostname);
            console.log('✅ CAST DEBUG: Replaced with hostname:', window.location.hostname);
        }
        console.log('🔗 CAST DEBUG: Final URL for casting:', absUrl);
    }
    
    const ext = absUrl.split('.').pop().toLowerCase();
    const mimeMap = {mp4:'video/mp4', webm:'video/webm', mkv:'video/x-matroska', mov:'video/quicktime', mp3:'audio/mpeg', m4a:'audio/mp4', opus:'audio/ogg', flac:'audio/flac'};
    const mime = mimeMap[ext] || 'video/mp4';
    console.log('🎬 CAST DEBUG: File extension:', ext, 'MIME type:', mime);
    
    console.log('🔄 CAST DEBUG: Creating media info object...');
    const mediaInfo = new chrome.cast.media.MediaInfo(absUrl, mime);
    mediaInfo.metadata = new chrome.cast.media.GenericMediaMetadata();
    mediaInfo.metadata.title = track.name;
    console.log('📝 CAST DEBUG: Media info created:', {
        contentId: mediaInfo.contentId,
        contentType: mediaInfo.contentType,
        title: mediaInfo.metadata.title
    });
    
    console.log('🚀 CAST DEBUG: Sending load request to cast device...');
    const request = new chrome.cast.media.LoadRequest(mediaInfo);
    session.loadMedia(request)
        .then(() => {
            console.log('✅ CAST DEBUG: Media loaded successfully on cast device!');
        })
        .catch(error => {
            console.error('❌ CAST DEBUG: Failed to load media on cast device:', error);
        });
}

/**
 * Sets up media ended event handler - handles track completion and auto-advance
 * @param {HTMLMediaElement} media - Audio/video element
 * @param {Object} context - Player context
 * @param {Array} context.queue - Current queue of tracks
 * @param {number|Function} context.currentIndex - Current track index (value or function)
 * @param {Function} context.reportEvent - Event reporting function
 * @param {Function} context.triggerAutoDeleteCheck - Auto-delete check function
 * @param {Function} context.playIndex - Play track by index function
 */
export function setupMediaEndedHandler(media, context) {
  media.addEventListener('ended', () => {
    // Get current index - handle both function and direct value
    const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
    
    // capture current track before any change
    const finishedTrack = context.queue[currentIndex];

    // report finish first
    if (finishedTrack) {
      context.reportEvent(finishedTrack.video_id, 'finish');
      
      // Trigger auto-delete check for channel content
      context.triggerAutoDeleteCheck(finishedTrack);
    }

    // then move to next track if available
    if (currentIndex + 1 < context.queue.length) {
      console.log(`🎵 Auto-advancing from track ${currentIndex} to ${currentIndex + 1}`);
      context.playIndex(currentIndex + 1);
    } else {
      console.log(`🏁 Reached end of queue at track ${currentIndex}, no more tracks to play`);
    }
  });
}

/**
 * Sets up media play/pause event handlers - manages UI icons and event reporting
 * @param {HTMLMediaElement} media - Audio/video element
 * @param {Object} context - Player context
 * @param {HTMLElement} context.cPlay - Play/pause button element
 * @param {Array} context.queue - Current queue of tracks
 * @param {number} context.currentIndex - Current track index
 * @param {Function} context.reportEvent - Event reporting function
 */
export function setupMediaPlayPauseHandlers(media, context) {
  media.addEventListener('play', () => {
    // Change to pause icon
    context.cPlay.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
    // Report play/resume event with current position
    if(context.currentIndex >= 0 && context.currentIndex < context.queue.length) {
      const track = context.queue[context.currentIndex];
      context.reportEvent(track.video_id, 'play', media.currentTime);
    }
  });
  
  media.addEventListener('pause', () => {
    // Change to play icon
    context.cPlay.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
    // Report pause event with current position
    if(context.currentIndex >= 0 && context.currentIndex < context.queue.length) {
      const track = context.queue[context.currentIndex];
      context.reportEvent(track.video_id, 'pause', media.currentTime);
    }
  });
}

/**
 * Sets up media timeupdate handler - updates progress bar and time display
 * @param {HTMLMediaElement} media - Audio/video element
 * @param {Object} context - Player context
 * @param {HTMLElement} context.progressBar - Progress bar element
 * @param {HTMLElement} context.timeLabel - Time label element
 * @param {Function} context.formatTime - Time formatting function
 */
export function setupMediaTimeUpdateHandler(media, context) {
  media.addEventListener('timeupdate', () => {
    const percent = (media.currentTime / media.duration) * 100;
    context.progressBar.style.width = `${percent}%`;
    context.timeLabel.textContent = `${context.formatTime(media.currentTime)} / ${context.formatTime(media.duration)}`;
  });
}

/**
 * Sets up media seeked handler - records seek events for analytics
 * @param {HTMLMediaElement} media - Audio/video element
 * @param {Object} context - Player context with seek state
 * @param {Array} context.queue - Current queue of tracks
 * @param {number|Function} context.currentIndex - Current track index (value or function)
 * @param {Function} context.recordSeekEvent - Seek event recording function
 * @param {Object} context.seekState - Seek state object (seekStartPosition)
 */
export function setupMediaSeekedHandler(media, context) {
  media.addEventListener('seeked', () => {
    // Get current index - handle both function and direct value
    const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
    
    if (context.seekState.seekStartPosition !== null && currentIndex >= 0 && currentIndex < context.queue.length) {
      const track = context.queue[currentIndex];
      const seekTo = media.currentTime;
      
      // Only record meaningful seeks (> 1 second difference)
      if (Math.abs(seekTo - context.seekState.seekStartPosition) >= 1.0) {
        console.log(`⏩ Seek recorded: ${Math.round(context.seekState.seekStartPosition)}s → ${Math.round(seekTo)}s for track "${track.name}"`);
        context.recordSeekEvent(track.video_id, context.seekState.seekStartPosition, seekTo, 'progress_bar');
      }
      
      context.seekState.seekStartPosition = null; // Reset
    }
  });
}

/**
 * Sets up keyboard event handler - handles all keyboard shortcuts
 * @param {Object} context - Player context
 * @param {Function} context.performKeyboardSeek - Keyboard seek function
 * @param {Function} context.nextTrack - Next track function
 * @param {Function} context.prevTrack - Previous track function
 * @param {Function} context.togglePlayback - Toggle playback function
 */
export function setupKeyboardHandler(context) {
  // Keyboard shortcuts: ← prev, → next, Space play/pause, Arrow Up/Down for seek
  document.addEventListener('keydown', (e) => {
    switch (e.code) {
      case 'ArrowRight':
        if (e.shiftKey) {
          // Shift + Right = Seek forward 10 seconds
          e.preventDefault();
          context.performKeyboardSeek(10);
        } else {
          context.nextTrack();
        }
        break;
      case 'ArrowLeft':
        if (e.shiftKey) {
          // Shift + Left = Seek backward 10 seconds
          e.preventDefault();
          context.performKeyboardSeek(-10);
        } else {
          context.prevTrack();
        }
        break;
      case 'ArrowUp':
        e.preventDefault();
        context.performKeyboardSeek(30); // Seek forward 30 seconds
        break;
      case 'ArrowDown':
        e.preventDefault();
        context.performKeyboardSeek(-30); // Seek backward 30 seconds
        break;
      case 'Space':
        e.preventDefault();
        context.togglePlayback();
        break;
    }
  });
}

/**
 * Sets up progress container click handler - handles seeking via progress bar clicks
 * @param {HTMLElement} progressContainer - Progress container element
 * @param {HTMLMediaElement} media - Audio/video element
 * @param {Object} context - Player context
 * @param {number|Function} context.currentIndex - Current track index (value or function)
 * @param {Function} context.sendStreamEvent - Stream event function
 * @param {Object} context.seekState - Seek state object (seekStartPosition)
 */
export function setupProgressClickHandler(progressContainer, media, context) {
  // Progress bar click handling with seek tracking
  progressContainer.onclick = (e) => {
    const rect = progressContainer.getBoundingClientRect();
    const pos = (e.clientX - rect.left) / rect.width;
    
    // Get current index - handle both function and direct value
    const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
    
    // Store seek start position
    context.seekState.seekStartPosition = media.currentTime;
    
    // Perform seek
    media.currentTime = pos * media.duration;
    
    // Send stream event
    context.sendStreamEvent({action:'seek', idx: currentIndex, paused: media.paused, position: media.currentTime});
    
    // Record seek event will happen in 'seeked' event listener
  };
}

/**
 * Sets up Media Session API handlers - enables media key controls
 * @param {Object} context - Player context
 * @param {Function} context.prevTrack - Previous track function
 * @param {Function} context.nextTrack - Next track function
 * @param {HTMLMediaElement} context.media - Audio/video element
 */
export function setupMediaSessionAPI(context) {
  // ---- Media Session API ----
  if ('mediaSession' in navigator) {
    navigator.mediaSession.setActionHandler('previoustrack', () => context.prevTrack());
    navigator.mediaSession.setActionHandler('nexttrack', () => context.nextTrack());
    navigator.mediaSession.setActionHandler('play', () => context.media.play());
    navigator.mediaSession.setActionHandler('pause', () => context.media.pause());
  }
}

/**
 * Sets up playlist toggle button handler - controls playlist visibility
 * @param {HTMLElement} toggleListBtn - Toggle list button element
 * @param {HTMLElement} playlistPanel - Playlist panel element
 */
export function setupPlaylistToggleHandler(toggleListBtn, playlistPanel) {
  // Playlist collapse/expand
  toggleListBtn.onclick = () => {
    playlistPanel.classList.toggle('collapsed');
    toggleListBtn.textContent = playlistPanel.classList.contains('collapsed') ? '☰ Show playlist' : '☰ Hide playlist';
    
    // Update track title and controls width after playlist toggle
    setTimeout(() => {
      if (typeof window.updateTrackTitleWidth === 'function') {
        window.updateTrackTitleWidth();
      }
    }, 300); // Wait for CSS transition to complete
  };
}

/**
 * Sets up delete current track button handler - handles track deletion with confirmation
 * @param {HTMLElement} deleteCurrentBtn - Delete current button element
 * @param {Object} context - execution context
 * @param {string} playerType - player type for logging ('regular' or 'virtual')
 */
export function setupDeleteCurrentHandler(deleteCurrentBtn, context, playerType = 'regular') {
    if (!deleteCurrentBtn) return;

    deleteCurrentBtn.onclick = async () => {
        // Get current index value (handle both direct values and functions)
        const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
        
        // Check if there's a current track
        if (currentIndex < 0 || currentIndex >= context.queue.length) {
            context.showNotification('❌ No active track to delete', 'error');
            return;
        }
        
        const currentTrack = context.queue[currentIndex];
        
        // Confirm deletion
        const confirmMessage = `Delete current track "${currentTrack.name.replace(/\s*\[.*?\]$/, '')}" from playlist?\n\nTrack will be moved to trash and can be restored.`;
        if (!confirm(confirmMessage)) {
            return;
        }
        
        // Execute deletion with confirmation
        await executeDeleteWithoutConfirmation(context, playerType);
    };
    
    // Store the function reference for remote commands
    deleteCurrentBtn.executeDeleteWithoutConfirmation = () => executeDeleteWithoutConfirmation(context, playerType);
}

/**
 * Sets up like and dislike button handlers
 * @param {HTMLElement} cLike - like button element
 * @param {HTMLElement} cDislike - dislike button element
 * @param {Object} context - context with necessary data
 * @param {number|Function} context.currentIndex - current track index
 * @param {Array} context.queue - track queue
 * @param {HTMLElement} context.media - media element
 * @param {Function} context.reportEvent - event reporting function
 * @param {Object} context.likedCurrent - like state (by reference)
 */
export function setupLikeDislikeHandlers(cLike, cDislike, context) {
    if (cLike) {
        cLike.onclick = () => {
            const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
            if (currentIndex < 0 || currentIndex >= context.queue.length) return;
            const track = context.queue[currentIndex];
            context.reportEvent(track.video_id, 'like', context.media.currentTime);
            context.likedCurrent = true;
            cLike.classList.add('like-active');
            // Change to filled heart (same icon, but red styling via CSS class)
            cLike.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>';
        };
    }

    if (cDislike) {
        cDislike.onclick = () => {
            const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
            if (currentIndex < 0 || currentIndex >= context.queue.length) return;
            const track = context.queue[currentIndex];
            context.reportEvent(track.video_id, 'dislike', context.media.currentTime);
            cDislike.classList.add('dislike-active');
            // Change to filled dislike (same icon, but purple styling via CSS class)
            cDislike.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z"></path></svg>';
        };
    }
}

/**
 * Sets up YouTube button handler - opens current track in YouTube
 * @param {HTMLElement} cYoutube - YouTube button element
 * @param {Object} context - context with necessary data
 * @param {number|Function} context.currentIndex - current track index
 * @param {Array} context.queue - track queue
 */
export function setupYouTubeHandler(cYoutube, context) {
    if (cYoutube) {
        cYoutube.onclick = () => {
            const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
            if (currentIndex < 0 || currentIndex >= context.queue.length) return;
            const track = context.queue[currentIndex];
            if (track.video_id) {
                const youtubeUrl = `https://www.youtube.com/watch?v=${track.video_id}`;
                window.open(youtubeUrl, '_blank');
            } else {
                console.warn('No video_id found for current track');
            }
        };
    }
}

/**
 * Sets up fullscreen button handlers - controls fullscreen mode
 * @param {HTMLElement} fullBtn - main fullscreen button element
 * @param {HTMLElement} cFull - fullscreen button element in controls
 * @param {HTMLElement} wrapper - container for fullscreen mode
 */
export function setupFullscreenHandlers(fullBtn, cFull, wrapper) {
    const fullscreenHandler = () => {
        if (!document.fullscreenElement) {
            wrapper.requestFullscreen?.() || wrapper.webkitRequestFullscreen?.();
        } else {
            document.exitFullscreen?.() || document.webkitExitFullscreen?.();
        }
    };

    if (fullBtn) {
        fullBtn.onclick = fullscreenHandler;
    }

    if (cFull) {
        cFull.onclick = fullscreenHandler;
    }
}

/**
 * Sets up simple control button handlers - basic playback controls
 * @param {HTMLElement} cPrev - previous track button element
 * @param {HTMLElement} cNext - next track button element
 * @param {HTMLElement} media - media element
 * @param {Function} prevTrack - previous track function
 * @param {Function} nextTrack - next track function
 * @param {Function} togglePlayback - toggle playback function
 */
export function setupSimpleControlHandlers(cPrev, cNext, media, prevTrack, nextTrack, togglePlayback) {
    if (cPrev) {
        cPrev.onclick = () => prevTrack();
    }

    if (cNext) {
        cNext.onclick = () => nextTrack();
    }

    // Clicking on the video toggles play/pause
    if (media) {
        media.addEventListener('click', togglePlayback);
    }
}

/**
 * Sets up stream button handler - creates and manages streaming sessions
 * @param {HTMLElement} streamBtn - stream button element (may be null in virtual player)
 * @param {Object} context - context with necessary data
 * @param {Object} context.streamIdLeader - current stream ID
 * @param {Array} context.queue - track queue
 * @param {Object} context.currentIndex - current track index
 * @param {HTMLElement} context.media - media element
 * @param {Function} context.sendStreamEvent - stream event function
 * @param {Function} context.startTick - start tick function
 */
export function setupStreamHandler(streamBtn, context) {
    // STREAM FUNCTIONALITY COMPLETELY DISABLED
    return;
    
    if (streamBtn) {
        streamBtn.onclick = async () => {
            const streamIdLeader = typeof context.streamIdLeader === 'function' ? context.streamIdLeader() : context.streamIdLeader;
            const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
            
            if (streamIdLeader) {
                alert('Stream already running. Share this URL:\n' + window.location.origin + '/stream/' + streamIdLeader);
                return;
            }
            const title = prompt('Stream title:', document.title);
            if (title === null) return;
            try {
                const body = {
                    title,
                    queue: context.queue,
                    idx: currentIndex,
                    paused: context.media.paused,
                    position: context.media.currentTime
                };
                const res = await fetch('/api/create_stream', { 
                    method: 'POST', 
                    headers: { 'Content-Type': 'application/json' }, 
                    body: JSON.stringify(body) 
                });
                const data = await res.json();
                // Note: Cannot set streamIdLeader directly if it's from a function - handled by caller
                streamBtn.textContent = 'Streaming…';
                streamBtn.disabled = true;
                if (!context.media.paused) {
                    context.sendStreamEvent({ action: 'play', position: context.media.currentTime, paused: false });
                    context.startTick();
                }
                const overlay = document.getElementById('shareOverlay');
                const linkEl = document.getElementById('shareLink');
                linkEl.href = data.url;
                linkEl.textContent = data.url;
                overlay.style.display = 'block';
                const copyBtn = document.getElementById('copyLinkBtn');
                copyBtn.onclick = () => {
                    if (!context.media.paused) { 
                        context.sendStreamEvent({ action: 'play' }); 
                    } // notify listeners to start
                    navigator.clipboard.writeText(data.url).catch(() => {});
                };
                document.getElementById('closeShare').onclick = () => overlay.style.display = 'none';
            } catch (err) { 
                alert('Stream creation failed: ' + err); 
            }
        };
    } else {
        console.warn('🔍 [DEBUG] streamBtn not found, streaming functionality disabled');
    }
}

/**
 * Sets up window beforeunload handler - stops tick timer when page is closed
 * @param {Function} stopTick - function to stop tick timer
 */
export function setupBeforeUnloadHandler(stopTick) {
    window.addEventListener('beforeunload', () => stopTick());
}

/**
 * Sets up auto-play initialization - starts playback and syncs on first load
 * @param {Array} queue - track queue
 * @param {Function} playIndex - function to play track by index
 * @param {Function} renderList - function to render track list
 * @param {Function} syncRemoteState - function to sync remote state
 */
export function setupAutoPlayInitialization(queue, playIndex, renderList, syncRemoteState) {
    // auto smart-shuffle and start playback on first load
    if (queue.length > 0) {
        playIndex(0);
        // Force sync after initial load
        setTimeout(syncRemoteState, 500);
    } else {
        renderList();
    }
}

/**
 * Sets up remote control function overrides - adds remote sync to existing functions
 * @param {Function} playIndex - original play index function
 * @param {Function} togglePlayback - original toggle playback function
 * @param {Function} syncRemoteState - function to sync remote state
 */
export function setupRemoteControlOverrides(playIndex, togglePlayback, syncRemoteState) {
    // Override existing functions to include remote sync
    const originalPlayIndex = playIndex;
    window.playIndex = function(idx) {
        originalPlayIndex.call(this, idx);
        setTimeout(syncRemoteState, 200);
    };
    
    const originalTogglePlayback = togglePlayback;
    window.togglePlayback = function() {
        originalTogglePlayback.call(this);
        setTimeout(syncRemoteState, 200);
    };
}

/**
 * Sets up remote control initialization - configures event listeners and periodic sync
 * @param {HTMLElement} media - media element
 * @param {Function} syncRemoteState - function to sync remote state
 * @param {Function} pollRemoteCommands - function to poll remote commands
 * @param {Object} context - context with current index
 */
export function setupRemoteControlInitialization(media, syncRemoteState, pollRemoteCommands, context) {
    // Enhanced event listeners for remote sync
    media.addEventListener('play', syncRemoteState);
    media.addEventListener('pause', syncRemoteState);
    media.addEventListener('loadeddata', syncRemoteState);
    media.addEventListener('timeupdate', () => {
        // Sync every 2 seconds during playback
        if (!media.paused && Math.floor(media.currentTime) % 2 === 0) {
            syncRemoteState();
        }
    });
    
    // Initial state sync after everything is loaded
    setTimeout(() => {
        const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
        if (currentIndex >= 0) {
            syncRemoteState();
        }
        // Start periodic sync every 3 seconds
        setInterval(syncRemoteState, 3000);
    }, 1000);
    
    // Periodic remote command polling (every 1 second)
    setInterval(pollRemoteCommands, 1000);
    
    console.log('🎮 Remote control synchronization initialized');
}