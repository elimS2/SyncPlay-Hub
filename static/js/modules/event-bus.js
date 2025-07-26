// Event bus functions extracted from player-utils.js

/**
 * Send stream event to server
 * @param {Object} payload - event data to send
 * @param {string|null} streamIdLeader - stream leader ID
 */
export async function sendStreamEvent(payload, streamIdLeader) {
  if(!streamIdLeader) return;
  try{
     await fetch(`/api/stream_event/${streamIdLeader}`, {
       method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
     });
  }catch(err){console.warn('stream_event failed', err);}
}

/**
 * Send analytics event to server
 * @param {string} videoId - video ID
 * @param {string} event - event type
 * @param {number|null} position - playback position (default null)
 */
export async function reportEvent(videoId, event, position = null) {
  if(!videoId) return;
  try{
     await fetch('/api/event', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({video_id: videoId, event, position})
     });
  }catch(err){
     console.warn('event report failed', err);
  }
}

/**
 * Send seek event to server for analytics
 * @param {string} video_id - video ID
 * @param {number} seek_from - initial seek position in seconds
 * @param {number} seek_to - final seek position in seconds
 * @param {string} source - seek source (progress_bar, keyboard, etc.)
 */
export async function recordSeekEvent(video_id, seek_from, seek_to, source) {
  try {
    const payload = {
      video_id: video_id,
      seek_from: seek_from,
      seek_to: seek_to,
      source: source
    };
    
    const response = await fetch('/api/seek', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (response.ok) {
      const data = await response.json();
      const direction = data.direction;
      const distance = Math.round(data.distance);
      console.log(`⏩ Seek ${direction}: ${Math.round(seek_from)}s → ${Math.round(seek_to)}s (${distance}s) via ${source}`);
    }
  } catch (error) {
    console.warn('⚠️ Failed to record seek event:', error);
  }
}

/**
 * Poll API for remote control commands and execute them
 * @param {Function} executeRemoteCommand - command execution function
 * @param {boolean} verbose - enable detailed logging (for virtual player)
 */
export async function pollRemoteCommands(executeRemoteCommand, verbose = false) {
    try {
        if (verbose) {
            console.log('🎮 [Virtual] Polling for remote commands...');
        }
        
        const response = await fetch('/api/remote/commands');
        
        if (verbose) {
            console.log('🎮 [Virtual] Poll response status:', response.status);
        }
        
        if (response.ok) {
            const commands = await response.json();
            
            if (verbose) {
                console.log('🎮 [Virtual] Poll response data:', commands);
                if (commands && commands.length > 0) {
                    console.log('🎮 [Virtual] Received commands:', commands);
                }
            }
            
            for (const command of commands) {
                try {
                    await executeRemoteCommand(command);
                } catch (error) {
                    console.error('🎮 [Remote] Error executing command:', command.type, error);
                }
            }
        } else if (verbose) {
            console.warn('🎮 [Virtual] Poll failed with status:', response.status);
        }
    } catch(err) {
        console.warn('Remote polling failed:', err);
    }
}

/**
 * Execute remote control commands with unified reliable logic
 * @param {Object} command - command to execute
 * @param {Object} context - execution context
 * @param {string} playerType - player type ('regular' or 'virtual') - for logging only
 */
export async function executeRemoteCommand(command, context, playerType = 'regular') {
    const { 
        media, nextTrack, prevTrack, stopPlayback, togglePlayback, 
        isVolumeWheelActive, cVol, updateMuteIcon,
        syncRemoteState, syncLikeButtonsWithRemote
    } = context;
    
    const logPrefix = playerType === 'virtual' ? '🎮 [Virtual Remote]' : '🎮 [Remote]';
    console.log(`${logPrefix} Executing command:`, command.type);
    
    try {
        switch(command.type) {
            case 'play':
                console.log(`${logPrefix} Toggle play/pause using unified logic`);
                togglePlayback(); // Unified: always use togglePlayback for reliability
                break;
                
            case 'next':
                console.log(`${logPrefix} Next track`);
                nextTrack();
                // Reset like buttons when track changes
                setTimeout(() => {
                    const likeBtn = document.getElementById('cLike');
                    const dislikeBtn = document.getElementById('cDislike');
                    if (likeBtn) likeBtn.classList.remove('like-active');
                    if (dislikeBtn) dislikeBtn.classList.remove('dislike-active');
                }, 100);
                break;
                
            case 'prev':
                console.log(`${logPrefix} Previous track`);
                prevTrack();
                // Reset like buttons when track changes
                setTimeout(() => {
                    const likeBtn = document.getElementById('cLike');
                    const dislikeBtn = document.getElementById('cDislike');
                    if (likeBtn) likeBtn.classList.remove('like-active');
                    if (dislikeBtn) dislikeBtn.classList.remove('dislike-active');
                }, 100);
                break;
                
            case 'stop':
                console.log(`${logPrefix} Stop playback`);
                stopPlayback();
                break;
                
            case 'volume':
                if (command.volume !== undefined) {
                    if (isVolumeWheelActive) {
                        break;
                    }
                    console.log(`${logPrefix} Set volume:`, Math.round(command.volume * 100) + '%');
                    media.volume = command.volume;
                    cVol.value = command.volume;
                    updateMuteIcon();
                    // Note: Volume is already saved by the remote API endpoint
                }
                break;
                
            case 'delete':
                console.log(`${logPrefix} Delete current track - checking button`);
                const deleteButton = document.getElementById('deleteCurrentBtn');
                console.log(`${logPrefix} deleteButton element:`, deleteButton);
                if (deleteButton) {
                    console.log(`${logPrefix} deleteCurrentBtn found, executing...`);
                    try {
                        // Check if this command came from remote control
                        if (command.from_remote) {
                            console.log(`${logPrefix} Command from remote - executing without confirmation`);
                            // Use the stored function for deletion without confirmation
                            if (deleteButton.executeDeleteWithoutConfirmation) {
                                await deleteButton.executeDeleteWithoutConfirmation();
                                console.log(`${logPrefix} Remote delete executed successfully`);
                            } else {
                                console.error(`${logPrefix} executeDeleteWithoutConfirmation function not found on button`);
                            }
                        } else {
                            // Regular click (will show confirmation dialog)
                            deleteButton.click();
                        }
                        console.log(`${logPrefix} deleteCurrentBtn execution completed`);
                    } catch (error) {
                        console.error(`${logPrefix} Error executing deleteCurrentBtn:`, error);
                    }
                } else {
                    console.error(`${logPrefix} deleteCurrentBtn not found!`);
                    console.log(`${logPrefix} Available buttons:`, document.querySelectorAll('button[id*="delete"]'));
                }
                break;
                
            case 'shuffle':
                console.log(`${logPrefix} Shuffle playlist - checking button`);
                const shuffleButton = document.getElementById('shuffleBtn');
                if (shuffleButton) {
                    console.log(`${logPrefix} shuffleBtn found, clicking...`);
                    shuffleButton.click();
                } else {
                    console.error(`${logPrefix} shuffleBtn not found!`);
                }
                break;
                
            case 'like':
                console.log(`${logPrefix} Like track - checking button`);
                const likeButton = document.getElementById('cLike');
                if (likeButton) {
                    console.log(`${logPrefix} cLike found, clicking...`);
                    likeButton.click();
                } else {
                    console.error(`${logPrefix} cLike button not found!`);
                }
                break;
                
            case 'dislike':
                console.log(`${logPrefix} Dislike track - checking button`);
                const dislikeButton = document.getElementById('cDislike');
                if (dislikeButton) {
                    console.log(`${logPrefix} cDislike found, clicking...`);
                    dislikeButton.click();
                } else {
                    console.error(`${logPrefix} cDislike button not found!`);
                }
                break;
                
            case 'youtube':
                console.log(`${logPrefix} Open YouTube - checking button`);
                const youtubeButton = document.getElementById('cYoutube');
                if (youtubeButton) {
                    console.log(`${logPrefix} cYoutube found, clicking...`);
                    youtubeButton.click();
                } else {
                    console.error(`${logPrefix} cYoutube button not found!`);
                }
                break;
                
            case 'fullscreen':
                console.log(`${logPrefix} Toggle fullscreen - checking button`);
                const fullscreenButton = document.getElementById('cFull');
                if (fullscreenButton) {
                    console.log(`${logPrefix} cFull found, clicking...`);
                    fullscreenButton.click();
                } else {
                    console.error(`${logPrefix} cFull button not found!`);
                }
                break;
                
            default:
                console.warn(`${logPrefix} Unknown command:`, command.type);
        }
        
        // Sync state after command execution
        setTimeout(syncRemoteState, 200);
        
        // Sync like buttons with remote state
        setTimeout(syncLikeButtonsWithRemote, 300);
    } catch (error) {
        console.error(`${logPrefix} Error executing command:`, error);
    }
} 