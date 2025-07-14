// Импорт общих утилит
import { shuffle, smartShuffle, detectChannelGroup, smartChannelShuffle, getGroupPlaybackInfo, orderByPublishDate as utilsOrderByPublishDate, formatTime, updateSpeedDisplay as utilsUpdateSpeedDisplay, showNotification, handleVolumeWheel as utilsHandleVolumeWheel, stopTick as utilsStopTick, stopPlayback as utilsStopPlayback, playIndex as utilsPlayIndex, updateMuteIcon as utilsUpdateMuteIcon, nextTrack as utilsNextTrack, prevTrack as utilsPrevTrack, sendStreamEvent as utilsSendStreamEvent, startTick as utilsStartTick, reportEvent as utilsReportEvent, triggerAutoDeleteCheck as utilsTriggerAutoDeleteCheck, recordSeekEvent, saveVolumeToDatabase as utilsSaveVolumeToDatabase, loadSavedVolume as utilsLoadSavedVolume, performKeyboardSeek as utilsPerformKeyboardSeek, syncLikeButtonsWithRemote as utilsSyncLikeButtonsWithRemote, syncLikesAfterAction as utilsSyncLikesAfterAction, setupLikeSyncHandlers as utilsSetupLikeSyncHandlers, togglePlayback as utilsTogglePlayback, showFsControls as utilsShowFsControls, updateFsVisibility as utilsUpdateFsVisibility, syncRemoteState as utilsSyncRemoteState, setupGlobalTooltip as utilsSetupGlobalTooltip, pollRemoteCommands as utilsPollRemoteCommands, cyclePlaybackSpeed as utilsCyclePlaybackSpeed, executeRemoteCommand as utilsExecuteRemoteCommand, deleteTrack as utilsDeleteTrack, initializeGoogleCastIntegration as utilsInitializeGoogleCastIntegration, castLoad as utilsCastLoad, loadTrack as utilsLoadTrack, setupMediaEndedHandler, setupMediaPlayPauseHandlers, setupMediaTimeUpdateHandler, setupMediaSeekedHandler, setupKeyboardHandler, setupProgressClickHandler, setupMediaSessionAPI, setupPlaylistToggleHandler, setupDeleteCurrentHandler, setupLikeDislikeHandlers, setupYouTubeHandler, setupFullscreenHandlers, setupSimpleControlHandlers, setupStreamHandler, setupBeforeUnloadHandler, setupAutoPlayInitialization, setupRemoteControlOverrides, setupRemoteControlInitialization } from '/static/js/modules/player-utils.js';

async function fetchTracks(playlistPath = '') {
  // For virtual playlists, get like count from global variable
  const likeCount = typeof VIRTUAL_PLAYLIST_LIKE_COUNT !== 'undefined' ? VIRTUAL_PLAYLIST_LIKE_COUNT : 1;
  
  console.log(`🔍 [Virtual] fetchTracks called for ${likeCount} likes`);
  
  try {
    const response = await fetch(`/api/tracks_by_likes/${likeCount}`);
    const data = await response.json();
    
    if (data.status === 'ok') {
      console.log(`✅ [Virtual] Successfully loaded ${data.tracks.length} tracks with ${likeCount} likes`);
      console.log(`📋 [Virtual] Track sample:`, data.tracks.slice(0, 3).map(t => t.name));
      return data.tracks;
    } else {
      throw new Error(data.message || 'API Error');
    }
  } catch (error) {
    console.error('❌ [Virtual] Error loading tracks:', error);
    return [];
  }
}

// shuffle() теперь импортируется из player-utils.js

// ===== SMART CHANNEL PLAYBACK LOGIC =====

// smartShuffle() теперь импортируется из player-utils.js

// detectChannelGroup() теперь импортируется из player-utils.js

// smartChannelShuffle() теперь импортируется из player-utils.js

// orderByPublishDate() теперь импортируется из player-utils.js
// Wrapper function для совместимости с существующим кодом
function orderByPublishDate(tracks) {
  // Используем схему 'virtual' для виртуальных плейлистов (timestamp, release_timestamp, release_year)
  return utilsOrderByPublishDate(tracks, 'virtual');
}

// getGroupPlaybackInfo() теперь импортируется из player-utils.js

// ===== END SMART CHANNEL PLAYBACK LOGIC =====

(async () => {
  const media = document.getElementById('player');
  const listElem = document.getElementById('tracklist');
  const shuffleBtn = document.getElementById('shuffleBtn');
  const smartShuffleBtn = document.getElementById('smartShuffleBtn');
  const deleteCurrentBtn = document.getElementById('deleteCurrentBtn');
  const fullBtn = document.getElementById('fullBtn');
  const cLike = document.getElementById('cLike');
const cDislike = document.getElementById('cDislike');
  const cYoutube = document.getElementById('cYoutube');
  let likedCurrent = false;
  const wrapper = document.getElementById('videoWrapper');
  const cPrev = document.getElementById('cPrev');
  const cPlay = document.getElementById('cPlay');
  const cNext = document.getElementById('cNext');
  const cFull = document.getElementById('cFull');
  const progressContainer = document.getElementById('progressContainer');
  const progressBar = document.getElementById('progressBar');
  const timeLabel = document.getElementById('timeLabel');
  const cMute = document.getElementById('cMute');
  const cVol = document.getElementById('cVol');
  const cSpeed = document.getElementById('cSpeed');
  const speedLabel = document.getElementById('speedLabel');
  const toggleListBtn = document.getElementById('toggleListBtn');
  const playlistPanel = document.getElementById('playlistPanel');
  const controlBar = document.getElementById('controlBar');
  const customControls = document.getElementById('customControls');
  let fsTimer;
  const streamBtn = document.getElementById('streamBtn');
  let streamIdLeader = null;
  let tickTimer=null;

  // Playback speed control
  const speedOptions = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5];
  let currentSpeedIndex = 2; // Default to 1x (index 2)

  const playlistRel = typeof PLAYLIST_REL !== 'undefined' ? PLAYLIST_REL : '';
  let tracks = await fetchTracks(playlistRel);

  let queue = smartChannelShuffle([...tracks]);
  let currentIndex = -1;
  
  // Log playback info
  const playbackInfo = getGroupPlaybackInfo(tracks);
  if (playbackInfo && playbackInfo.length > 0) {
    console.log('🎯 Smart Playback Info:');
    playbackInfo.forEach(info => {
      const icon = info.type === 'music' ? '🎵' : 
                   info.type === 'news' ? '📰' : 
                   info.type === 'education' ? '🎓' : 
                   info.type === 'podcasts' ? '🎙️' : '📋';
      console.log(`  ${icon} ${info.group}: ${info.count} tracks (${info.isChannel ? 'Channel' : 'Playlist'})`);
    });
  }

  if (tracks.length === 0) {
    console.warn('❌ No tracks loaded - check API endpoint');
  } else if (queue.length === 0) {
    console.warn('❌ Queue is empty - check smartChannelShuffle function');
  } else {
    console.log('✅ Data looks good, rendering playlist...');
    renderList();
    console.log('✅ Playlist rendered successfully');
  }

  // ---- Google Cast Integration ----
  // Используем централизованную функцию инициализации Cast
  const castState = utilsInitializeGoogleCastIntegration({ 
    currentIndex, 
    queue, 
    castLoad: (track) => castLoad(track) 
  });
  let castContext = castState.castContext;
  let pendingCastTrack = castState.pendingCastTrack;

  function castLoad(track){
      return utilsCastLoad(track, {
          castContext,
          setPendingCastTrack: (t) => { pendingCastTrack = t; }
          });
  }

  if(window.cast && castContext){
      castContext.addEventListener(cast.framework.CastContextEventType.SESSION_STATE_CHANGED, (e)=>{
          if((e.sessionState===cast.framework.SessionState.SESSION_STARTED || e.sessionState===cast.framework.SessionState.SESSION_RESUMED) && pendingCastTrack){
              castLoad(pendingCastTrack);
              pendingCastTrack=null;
          }
      });
  }

  console.log('🔍 [DEBUG] Cast integration completed, starting main player logic...');

  function renderList() {
    listElem.innerHTML = '';
    queue.forEach((t, idx) => {
      const li = document.createElement('li');
      li.dataset.index = idx;
      if (idx === currentIndex) li.classList.add('playing');
      
      // Create custom tooltip with SVG icons (identical to player.js)
      let tooltipHTML = '';
      
      // DEBUG: Log track data for first few tracks
      if (idx < 3) {
        console.log(`🔍 [DEBUG] Track ${idx + 1} data:`, t);
        console.log(`🔍 [DEBUG] youtube_channel_handle: ${t.youtube_channel_handle}`);
        console.log(`🔍 [DEBUG] youtube_timestamp: ${t.youtube_timestamp}`);
        console.log(`🔍 [DEBUG] youtube_view_count: ${t.youtube_view_count}`);
        console.log(`🔍 [DEBUG] youtube_metadata_updated: ${t.youtube_metadata_updated}`);
        console.log(`🔍 [DEBUG] youtube_duration_string: ${t.youtube_duration_string}`);
      }
      
      // Add channel handle (@channelname) info - FIRST ITEM
      if (t.youtube_channel_handle) {
        tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg><strong>Channel:</strong> ${t.youtube_channel_handle}</div>`;
      }
      
      // Add YouTube publish date info
      if (t.youtube_timestamp || t.youtube_release_timestamp || t.youtube_release_year) {
        let publishDate = 'Unknown';
        
        if (t.youtube_timestamp) {
          const date = new Date(t.youtube_timestamp * 1000);
          publishDate = date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
          });
        } else if (t.youtube_release_timestamp) {
          const date = new Date(t.youtube_release_timestamp * 1000);
          publishDate = date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
          });
        } else if (t.youtube_release_year) {
          publishDate = t.youtube_release_year;
        }
        
        tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg><strong>Publish Date:</strong> ${publishDate}</div>`;
      } else {
        tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg><strong>Publish Date:</strong> Unknown</div>`;
      }
      
      // Add YouTube view count info
      if (t.youtube_view_count !== undefined && t.youtube_view_count !== null) {
        const viewCount = Number(t.youtube_view_count).toLocaleString();
        tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg><strong>YouTube Views:</strong> ${viewCount}</div>`;
      }
      
      // Add metadata sync date info
      if (t.youtube_metadata_updated) {
        try {
          const syncDate = new Date(t.youtube_metadata_updated);
          const syncFormatted = syncDate.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
          });
          tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"></path></svg><strong>Metadata Synced:</strong> ${syncFormatted}</div>`;
        } catch (e) {
          tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"></path></svg><strong>Metadata Synced:</strong> Unknown</div>`;
        }
      }
      
      // Add video duration info
      if (t.youtube_duration_string) {
        tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg><strong>Duration:</strong> ${t.youtube_duration_string}</div>`;
      } else if (t.youtube_duration) {
        const duration = Math.floor(t.youtube_duration);
        const minutes = Math.floor(duration / 60);
        const seconds = duration % 60;
        const durationStr = `${minutes}:${seconds.toString().padStart(2, '0')}`;
        tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg><strong>Duration:</strong> ${durationStr}</div>`;
      }
      
      // Add last play date info
      if (t.last_play) {
        try {
          const lastPlayDate = new Date(t.last_play.replace(' ', 'T') + 'Z');
          const lastPlayFormatted = lastPlayDate.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
          });
          tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg><strong>Last Played:</strong> ${lastPlayFormatted}</div>`;
        } catch (e) {
          tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg><strong>Last Played:</strong> Never</div>`;
        }
      } else {
        tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg><strong>Last Played:</strong> Never</div>`;
      }
      
      // Add playback statistics
      tooltipHTML += `<div class="tooltip-section"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"></line><line x1="18" y1="20" x2="18" y2="4"></line><line x1="6" y1="20" x2="6" y2="16"></line></svg><strong>Playback Statistics:</strong></div>`;
      tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5,3 19,12 5,21"></polygon></svg>Total Plays: ${t.play_starts || 0}</div>`;
      tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"></polyline></svg>Completed Plays: ${t.play_finishes || 0}</div>`;
      tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5,4 15,12 5,20"></polygon><line x1="19" y1="5" x2="19" y2="19"></line></svg>Next Button Clicks: ${t.play_nexts || 0}</div>`;
      const netLikes = (t.play_likes || 0) - (t.play_dislikes || 0);
      tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>Likes: ${t.play_likes || 0}</div>`;
      tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9b59b6" stroke-width="2"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z"></path></svg>Dislikes: ${t.play_dislikes || 0}</div>`;
      tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4CAF50" stroke-width="2"><path d="M9 12l2 2 4-4"></path><circle cx="12" cy="12" r="10"></circle></svg><strong>Net Likes: ${netLikes}</strong></div>`;
      
      // Store tooltip content in data attribute
      li.setAttribute('data-tooltip-html', tooltipHTML);
      
      // Create track content container
      const trackContent = document.createElement('div');
      trackContent.className = 'track-content';
      trackContent.style.cssText = 'display: flex; justify-content: space-between; align-items: center; width: 100%;';
      
      // Track name and number
      const trackInfo = document.createElement('div');
      trackInfo.className = 'track-info';
      trackInfo.style.cssText = 'flex: 1; cursor: pointer;';
      const displayName = t.name.replace(/\s*\[.*?\]$/, '');
      trackInfo.textContent = `${idx + 1}. ${displayName}`;
      trackInfo.onclick = () => playIndex(idx);
      
      // Delete button
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'delete-btn';
      deleteBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c0 1 1 2 1 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>';
      deleteBtn.title = 'Delete track';
      deleteBtn.style.cssText = `
        background: none;
        border: none;
        color: #ff4444;
        cursor: pointer;
        font-size: 16px;
        padding: 4px 8px;
        border-radius: 4px;
        margin-left: 8px;
        opacity: 0.7;
        transition: opacity 0.2s ease, background-color 0.2s ease;
      `;
      
      // Hover effects for delete button
      deleteBtn.onmouseenter = () => {
        deleteBtn.style.opacity = '1';
        deleteBtn.style.backgroundColor = 'rgba(255, 68, 68, 0.1)';
      };
      deleteBtn.onmouseleave = () => {
        deleteBtn.style.opacity = '0.7';
        deleteBtn.style.backgroundColor = 'transparent';
      };
      
      deleteBtn.onclick = (e) => {
        e.stopPropagation(); // Prevent track selection
        deleteTrack(t, idx);
      };
      
      trackContent.appendChild(trackInfo);
      trackContent.appendChild(deleteBtn);
      li.appendChild(trackContent);
      listElem.appendChild(li);
    });
    
    console.log(`🎵 Rendered ${queue.length} tracks in playlist`);
    
    // Create global tooltip system (like in player.js)
    setupGlobalTooltip();
  }

  function loadTrack(idx, autoplay=false){
    return utilsLoadTrack(idx, autoplay, {
        queue, currentIndex, setCurrentIndex: (newIdx) => { currentIndex = newIdx; },
        media, speedOptions, currentSpeedIndex, castLoad, renderList,
        cLike, cDislike, reportEvent, sendStreamEvent
    });
  }

  function playIndex(idx){
    utilsPlayIndex(idx, loadTrack);
  }

  // Setup media ended handler using centralized function
  setupMediaEndedHandler(media, {
    queue,
    currentIndex: () => currentIndex,
    reportEvent,
    triggerAutoDeleteCheck,
    playIndex
  });

  shuffleBtn.onclick = () => {
    // Regular random shuffle
    queue = [...tracks];
    shuffle(queue);
    console.log('🔀 Random shuffle applied to all tracks');
    playIndex(0);
  };

  smartShuffleBtn.onclick = ()=>{
     // Smart channel-aware shuffle
     queue = smartChannelShuffle([...tracks]);
     console.log('🧠 Smart channel shuffle applied');
     
     // Log playback info
     const playbackInfo = getGroupPlaybackInfo(tracks);
     if (playbackInfo && playbackInfo.length > 0) {
       console.log('🎯 Updated Playback Info:');
       playbackInfo.forEach(info => {
         const icon = info.type === 'music' ? '🎵' : 
                      info.type === 'news' ? '📰' : 
                      info.type === 'education' ? '🎓' : 
                      info.type === 'podcasts' ? '🎙️' : '📋';
         console.log(`  ${icon} ${info.group}: ${info.count} tracks (${info.isChannel ? 'Channel' : 'Playlist'})`);
       });
     }
     
     playIndex(0);
  };

  orderByDateBtn.onclick = () => {
    // Sort tracks by YouTube publish date (oldest first)
    queue = orderByPublishDate([...tracks]);
    console.log('📅 [Virtual] Tracks ordered by YouTube publish date (oldest first)');
    playIndex(0);
  };

  // Direct functions for playback control
  function stopPlayback() {
    utilsStopPlayback(media);
  }

  function nextTrack() {
    utilsNextTrack(currentIndex, queue, reportEvent, playIndex, sendStreamEvent, media);
  }

  function prevTrack() {
    utilsPrevTrack(currentIndex, queue, reportEvent, playIndex, sendStreamEvent, media);
  }

  // togglePlayback() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  function togglePlayback() {
    return utilsTogglePlayback({ media, sendStreamEvent, startTick });
  }

  // Setup delete current button handler using centralized function
  setupDeleteCurrentHandler(deleteCurrentBtn, {
    currentIndex: () => currentIndex,
    queue,
    tracks,
    media,
    playIndex,
    renderList,
    showNotification,
    loadTrack
  }, 'virtual');

  // Setup fullscreen and control handlers using centralized functions
  setupFullscreenHandlers(fullBtn, cFull, wrapper);
  setupSimpleControlHandlers(cPrev, cNext, media, prevTrack, nextTrack, togglePlayback);

  // Speed control functionality
  // updateSpeedDisplay() теперь импортируется из player-utils.js
  function updateSpeedDisplay() {
    // Wrapper function для совместимости с существующим кодом
    return utilsUpdateSpeedDisplay(currentSpeedIndex, speedOptions, speedLabel, cSpeed);
  }

  // cyclePlaybackSpeed() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function cyclePlaybackSpeed() {
    const context = { currentSpeedIndex, speedOptions, media, updateSpeedDisplay, reportEvent, currentIndex, queue };
    const newSpeedIndex = await utilsCyclePlaybackSpeed(context, null, 'virtual');
    currentSpeedIndex = newSpeedIndex;
    updateSpeedDisplay(); // Update display after index is updated
  }

  // Initialize speed display
  updateSpeedDisplay();

  // Speed control button click handler
  if (cSpeed) {
    cSpeed.onclick = cyclePlaybackSpeed;
  }

  cPlay.onclick = togglePlayback;

  // Setup media play/pause handlers using centralized function
  setupMediaPlayPauseHandlers(media, {
    cPlay,
    queue,
    currentIndex,
    reportEvent
  });

  // formatTime() теперь импортируется из player-utils.js

  // Setup media timeupdate handler using centralized function
  setupMediaTimeUpdateHandler(media, {
    progressBar,
    timeLabel,
    formatTime
  });

  // Track seek events
  let lastSeekPosition = null;
  const seekState = { seekStartPosition: null };
  
  // Setup progress container click handler using centralized function
  setupProgressClickHandler(progressContainer, media, {
    currentIndex: () => currentIndex,
    sendStreamEvent,
    seekState
  });
  
  // Setup media seeked handler using centralized function
  setupMediaSeekedHandler(media, {
    queue,
    currentIndex: () => currentIndex,
    recordSeekEvent,
    seekState
  });
  
  // recordSeekEvent() теперь импортируется из player-utils.js

  // cFull.onclick теперь обрабатывается в setupFullscreenHandlers()

  // Volume wheel control variables - defined early for scope access
  let volumeWheelTimeout = null;
  let isVolumeWheelActive = false;
  
  // Object для передачи состояния в handleVolumeWheel
  const volumeState = {
    isVolumeWheelActive: false,
    volumeWheelTimeout: null
  };
  
  // Volume logic
  cMute.onclick = () => {
    media.muted = !media.muted;
    updateMuteIcon();
  };
  cVol.oninput = () => {
    if (isVolumeWheelActive) {
      return;
    }
    media.volume = parseFloat(cVol.value);
    media.muted = media.volume === 0;
    updateMuteIcon();
    saveVolumeToDatabase(media.volume);
  };
  
  // Volume wheel control - adjust volume by 1% with mouse wheel
  
  if (cVol) {
    
    // handleVolumeWheel() теперь импортируется из player-utils.js
    function handleVolumeWheel(e) {
      // Wrapper function для совместимости с существующим кодом
      // Update local state for backward compatibility
      volumeState.isVolumeWheelActive = true;
      clearTimeout(volumeState.volumeWheelTimeout);
      volumeState.volumeWheelTimeout = setTimeout(() => {
        volumeState.isVolumeWheelActive = false;
      }, 2000);
      
      // Также обновляем старые переменные для совместимости
      isVolumeWheelActive = volumeState.isVolumeWheelActive;
      volumeWheelTimeout = volumeState.volumeWheelTimeout;
      
      return utilsHandleVolumeWheel(e, cVol, media, updateMuteIcon, saveVolumeToDatabase, volumeState);
    }
    
    // Add wheel event listeners for cross-browser compatibility
    cVol.addEventListener('wheel', handleVolumeWheel, { passive: false });
    cVol.addEventListener('mousewheel', handleVolumeWheel, { passive: false }); // For older browsers
    cVol.addEventListener('DOMMouseScroll', handleVolumeWheel, { passive: false }); // For Firefox
    
    console.log('✅ Volume wheel control setup complete with cross-browser support');
  } else {
    console.error('❌ cVol element not found - wheel control not initialized');
  }
  
  function updateMuteIcon() {
    utilsUpdateMuteIcon(media, cMute);
  }
  
  // Save volume to database with debouncing
  let volumeSaveTimeout = null;
  let lastSavedVolume = null;
  
  // saveVolumeToDatabase() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function saveVolumeToDatabase(volume) {
    const context = {
      currentIndex,
      queue,
      media,
      state: { volumeSaveTimeout, lastSavedVolume }
    };
    await utilsSaveVolumeToDatabase(volume, context);
    
    // Update local state after save
    volumeSaveTimeout = context.state.volumeSaveTimeout;
    lastSavedVolume = context.state.lastSavedVolume;
  }

  // loadSavedVolume() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function loadSavedVolume() {
    const state = { lastSavedVolume };
    await utilsLoadSavedVolume(media, cVol, state, updateMuteIcon);
    
    // Update local state after load
    lastSavedVolume = state.lastSavedVolume;
  }
  
  // Load saved volume immediately
  loadSavedVolume();

  // Setup auto-play initialization using centralized function
  setupAutoPlayInitialization(queue, playIndex, renderList, syncRemoteState);

  // Setup keyboard handler using centralized function
  setupKeyboardHandler({
    performKeyboardSeek,
    nextTrack,
    prevTrack,
    togglePlayback
  });
  
  // performKeyboardSeek() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  function performKeyboardSeek(offsetSeconds) {
    const context = { currentIndex, queue, media, recordSeekEvent };
    return utilsPerformKeyboardSeek(offsetSeconds, context);
  }

  // showFsControls() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  function showFsControls(){
    return utilsShowFsControls({ customControls, controlBar, fsTimer });
  }

  // updateFsVisibility() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  function updateFsVisibility(){
    return utilsUpdateFsVisibility({ listElem, customControls, controlBar, wrapper, fsTimer });
  }
  document.addEventListener('fullscreenchange', updateFsVisibility);
  updateFsVisibility();

  // Setup Media Session API using centralized function
  setupMediaSessionAPI({
    prevTrack,
    nextTrack,
    media
  });

  // media click handler теперь обрабатывается в setupSimpleControlHandlers()

  // Setup playlist toggle handler using centralized function
  setupPlaylistToggleHandler(toggleListBtn, playlistPanel);

  // Setup like/dislike and YouTube handlers using centralized functions
  setupLikeDislikeHandlers(cLike, cDislike, {
    currentIndex: () => currentIndex,
    queue,
    media,
    reportEvent,
    likedCurrent
  });
  
  setupYouTubeHandler(cYoutube, {
    currentIndex: () => currentIndex,
    queue
  });

  async function reportEvent(videoId, event, position=null){
    await utilsReportEvent(videoId, event, position);
  }

  async function triggerAutoDeleteCheck(track) {
    await utilsTriggerAutoDeleteCheck(track, detectChannelGroup, media);
  }

  async function sendStreamEvent(payload){
    await utilsSendStreamEvent(payload, streamIdLeader);
  }

  function startTick(){
    tickTimer = utilsStartTick(tickTimer, streamIdLeader, sendStreamEvent, currentIndex, media);
  }
  function stopTick() { 
    tickTimer = utilsStopTick(tickTimer); 
  }

  // Setup stream handler using centralized function
  setupStreamHandler(streamBtn, {
    streamIdLeader: () => streamIdLeader,
           queue,
    currentIndex: () => currentIndex,
    media,
    sendStreamEvent,
    startTick
  });

  // Setup beforeunload handler using centralized function
  setupBeforeUnloadHandler(stopTick);

  // ==============================
  // REMOTE CONTROL SYNCHRONIZATION
  // ==============================
  
  console.log('🔍 [DEBUG] About to start remote control setup...');
  
  // syncRemoteState() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function syncRemoteState() {
    return await utilsSyncRemoteState('virtual', { currentIndex, queue, media });
  }
  
  // pollRemoteCommands() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function pollRemoteCommands() {
    return await utilsPollRemoteCommands(executeRemoteCommand, true); // verbose=true для virtual
  }
  
  // executeRemoteCommand() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function executeRemoteCommand(command) {
    const context = {
      media, nextTrack, prevTrack, stopPlayback, togglePlayback, 
      isVolumeWheelActive, cVol, updateMuteIcon,
      syncRemoteState, syncLikeButtonsWithRemote
    };
    return await utilsExecuteRemoteCommand(command, context, 'virtual');
  }
  
  // syncLikeButtonsWithRemote() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function syncLikeButtonsWithRemote() {
    return await utilsSyncLikeButtonsWithRemote();
  }
  
  // Setup remote control using centralized functions  
  setupRemoteControlOverrides(playIndex, togglePlayback, syncRemoteState);
  setupRemoteControlInitialization(media, syncRemoteState, pollRemoteCommands, { currentIndex: () => currentIndex });
  
  // deleteTrack() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function deleteTrack(track, trackIndex) {
    const context = {
      queue, tracks, currentIndex, media, playIndex, renderList, 
      showNotification, loadTrack,
      getCurrentIndex: () => currentIndex,
      setCurrentIndex: (newIdx) => { currentIndex = newIdx; }
    };
    return await utilsDeleteTrack(track, trackIndex, context); // Используется универсальная логика с file locks
  }

  // showNotification() теперь импортируется из player-utils.js

  // setupGlobalTooltip() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  function setupGlobalTooltip() {
    return utilsSetupGlobalTooltip(listElem);
  }

  // Tooltip system will be initialized after rendering tracks in renderList()
  
  // Tooltip system will be initialized in renderList() after tracks are rendered
  
  // ==============================
  // LIKE SYNCHRONIZATION
  // ==============================
  
  // syncLikesAfterAction() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function syncLikesAfterAction(video_id, action) {
    return await utilsSyncLikesAfterAction(video_id, action, syncRemoteState);
  }
  
  // setupLikeSyncHandlers() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  function setupLikeSyncHandlers() {
    const context = { currentIndex, queue, syncLikesAfterAction };
    return utilsSetupLikeSyncHandlers(context);
  }
  
  // Initialize like sync when page loads
  window.addEventListener('DOMContentLoaded', function() {
    console.log('🎵 [Like Sync] Initializing like synchronization...');
    setupLikeSyncHandlers();
    
    // Start periodic sync with remote control for likes
    setInterval(async () => {
      if (typeof syncLikeButtonsWithRemote === 'function') {
        await syncLikeButtonsWithRemote();
      }
    }, 3000); // Check every 3 seconds
  });
  
  // Override loadTrack to reset like buttons when track changes
  const originalLoadTrack = loadTrack;
  window.loadTrack = function(idx, autoplay = false) {
    // Call original function
    originalLoadTrack.call(this, idx, autoplay);
    
    // Reset like buttons for new track (session-based)
    const likeButton = document.getElementById('cLike');
    const dislikeButton = document.getElementById('cDislike');
    
    if (likeButton) {
      likeButton.classList.remove('like-active');
    }
    if (dislikeButton) {
      dislikeButton.classList.remove('dislike-active');
    }
    
    // Sync remote state after track change to update button states
    setTimeout(() => {
      syncRemoteState();
    }, 200);
  };

  })(); 