// Импорт общих утилит из нового barrel файла
import { shuffle, smartShuffle, detectChannelGroup, smartChannelShuffle, getGroupPlaybackInfo, orderByPublishDate as utilsOrderByPublishDate, formatTime, updateSpeedDisplay as utilsUpdateSpeedDisplay, showNotification, handleVolumeWheel as utilsHandleVolumeWheel, stopTick as utilsStopTick, stopPlayback as utilsStopPlayback, playIndex as utilsPlayIndex, updateMuteIcon as utilsUpdateMuteIcon, nextTrack as utilsNextTrack, prevTrack as utilsPrevTrack, sendStreamEvent as utilsSendStreamEvent, startTick as utilsStartTick, reportEvent as utilsReportEvent, triggerAutoDeleteCheck as utilsTriggerAutoDeleteCheck, recordSeekEvent, saveVolumeToDatabase as utilsSaveVolumeToDatabase, loadSavedVolume as utilsLoadSavedVolume, performKeyboardSeek as utilsPerformKeyboardSeek, syncLikeButtonsWithRemote as utilsSyncLikeButtonsWithRemote, syncLikesAfterAction as utilsSyncLikesAfterAction, setupLikeSyncHandlers as utilsSetupLikeSyncHandlers, togglePlayback as utilsTogglePlayback, showFsControls as utilsShowFsControls, updateFsVisibility as utilsUpdateFsVisibility, syncRemoteState as utilsSyncRemoteState, setupGlobalTooltip as utilsSetupGlobalTooltip, createTrackTooltipHTML, pollRemoteCommands as utilsPollRemoteCommands, cyclePlaybackSpeed as utilsCyclePlaybackSpeed, executeRemoteCommand as utilsExecuteRemoteCommand, deleteTrack as utilsDeleteTrack, initializeGoogleCastIntegration as utilsInitializeGoogleCastIntegration, castLoad as utilsCastLoad, loadTrack as utilsLoadTrack, setupMediaEndedHandler, setupMediaPlayPauseHandlers, setupMediaTimeUpdateHandler, setupMediaSeekedHandler, setupKeyboardHandler, setupProgressClickHandler, setupMediaSessionAPI, setupPlaylistToggleHandler, setupDeleteCurrentHandler, setupLikeDislikeHandlers, setupYouTubeHandler, setupFullscreenHandlers, setupSimpleControlHandlers, setupStreamHandler, setupBeforeUnloadHandler, setupAutoPlayInitialization, setupRemoteControlOverrides, setupRemoteControlInitialization } from '/static/js/modules/index.js';

// Импорт track title manager
import { updateCurrentTrackTitle } from '/static/js/modules/track-title-manager.js';

async function fetchTracks(playlistPath = '') {
  const endpoint = playlistPath ? `/api/tracks/${encodeURI(playlistPath)}` : '/api/tracks';
  const res = await fetch(endpoint);
  return await res.json();
}

// shuffle() теперь импортируется из player-utils.js

// ===== SMART CHANNEL PLAYBACK LOGIC =====

// smartShuffle() теперь импортируется из player-utils.js

// detectChannelGroup() теперь импортируется из player-utils.js

// smartChannelShuffle() теперь импортируется из player-utils.js

// orderByPublishDate() теперь импортируется из player-utils.js
// Wrapper function для совместимости с существующим кодом
function orderByPublishDate(tracks) {
  // Используем схему 'regular' для обычных плейлистов (youtube_timestamp, youtube_release_timestamp, youtube_release_year)
  return utilsOrderByPublishDate(tracks, 'regular');
}

// getGroupPlaybackInfo() теперь импортируется из player-utils.js

// ===== END SMART CHANNEL PLAYBACK LOGIC =====

(async () => {
  const media = document.getElementById('player');
  const listElem = document.getElementById('tracklist');
  const shuffleBtn = document.getElementById('shuffleBtn');
  const smartShuffleBtn = document.getElementById('smartShuffleBtn');
  const orderByDateBtn = document.getElementById('orderByDateBtn');
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

  // Playlist preferences functions
  async function savePlaylistPreference(preference) {
    if (!playlistRel) return;
    
    try {
      const response = await fetch('/api/save_display_preference', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          relpath: playlistRel,
          preference: preference
        })
      });
      
      const result = await response.json();
      if (result.status === 'ok') {
        console.log(`💾 Playlist preference saved: ${preference}`);
      } else {
        console.warn('❌ Failed to save playlist preference:', result.message);
      }
    } catch (error) {
      console.error('❌ Error saving playlist preference:', error);
    }
  }

  // Playlist speed functions
  async function savePlaylistSpeed(speed) {
    if (!playlistRel) return;
    
    try {
      const response = await fetch('/api/save_playback_speed', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          relpath: playlistRel,
          speed: speed
        })
      });
      
      const result = await response.json();
      if (result.status === 'ok') {
        console.log(`⚡ Playlist speed saved: ${speed}x`);
      } else {
        console.warn('❌ Failed to save playlist speed:', result.message);
      }
    } catch (error) {
      console.error('❌ Error saving playlist speed:', error);
    }
  }

  async function loadPlaylistSpeed() {
    if (!playlistRel) return 1.0; // Default fallback
    
    try {
      const response = await fetch(`/api/get_playback_speed?relpath=${encodeURIComponent(playlistRel)}`);
      const result = await response.json();
      
      if (result.status === 'ok') {
        console.log(`⚡ Loaded playlist speed: ${result.speed}x`);
        return result.speed;
      } else {
        console.warn('❌ Failed to load playlist speed:', result.message);
        return 1.0; // Default fallback
      }
    } catch (error) {
      console.error('❌ Error loading playlist speed:', error);
      return 1.0; // Default fallback
    }
  }

  async function loadPlaylistPreference() {
    if (!playlistRel) return 'shuffle'; // Default fallback
    
    try {
      const response = await fetch(`/api/get_display_preference?relpath=${encodeURIComponent(playlistRel)}`);
      const result = await response.json();
      
      if (result.status === 'ok') {
        console.log(`📂 Loaded playlist preference: ${result.preference}`);
        return result.preference;
      } else {
        console.warn('❌ Failed to load playlist preference:', result.message);
        return 'shuffle'; // Default fallback
      }
    } catch (error) {
      console.error('❌ Error loading playlist preference:', error);
      return 'shuffle'; // Default fallback
    }
  }

  // Apply display preference
  async function applyDisplayPreference(preference) {
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
  }

  // Load saved preference and apply it
  const savedPreference = await loadPlaylistPreference();
  let queue = []; // Initialize queue
  await applyDisplayPreference(savedPreference);

  // Load and apply saved playback speed
  const savedSpeed = await loadPlaylistSpeed();
  const speedIndex = speedOptions.indexOf(savedSpeed);
  if (speedIndex !== -1) {
    currentSpeedIndex = speedIndex;
    console.log(`⚡ Applied saved speed: ${savedSpeed}x`);
  } else {
    console.warn(`⚠️ Invalid saved speed ${savedSpeed}x, using default 1x`);
    currentSpeedIndex = 2; // Default to 1x (index 2)
  }
  
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

  function renderList() {
    console.log(`🎵 [DEBUG] renderList called, queue length: ${queue.length}, currentIndex: ${currentIndex}`);
    listElem.innerHTML = '';
    queue.forEach((t, idx) => {
      const li = document.createElement('li');
      li.dataset.index = idx;
      if (idx === currentIndex) li.classList.add('playing');
      
      // Create custom tooltip using centralized function
      const tooltipHTML = createTrackTooltipHTML(t);
      
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
    
    // Update current track title display after rendering list
    if (currentIndex >= 0 && currentIndex < queue.length) {
      const currentTrack = queue[currentIndex];
      updateCurrentTrackTitle(currentTrack);
    }
    
    // Create global tooltip system
    setupGlobalTooltip();
  }
  
  // setupGlobalTooltip() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  function setupGlobalTooltip() {
    return utilsSetupGlobalTooltip(listElem);
  }

  function loadTrack(idx, autoplay=false){
    console.log(`🎵 [DEBUG] loadTrack called with idx: ${idx}, autoplay: ${autoplay}`);
    console.log(`🎵 [DEBUG] queue length: ${queue.length}, currentIndex: ${currentIndex}`);
    
    const result = utilsLoadTrack(idx, autoplay, {
        queue, currentIndex, setCurrentIndex: (newIdx) => { 
          console.log(`🎵 [DEBUG] Setting currentIndex from ${currentIndex} to ${newIdx}`);
          currentIndex = newIdx; 
        },
        media, speedOptions, currentSpeedIndex, castLoad, renderList,
        cLike, cDislike, reportEvent, sendStreamEvent
    });
    
    // Update track title display
    if (idx >= 0 && idx < queue.length) {
      console.log(`🎵 [DEBUG] Updating track title for track: ${queue[idx].name}`);
      updateCurrentTrackTitle(queue[idx]);
    } else {
      console.warn(`🎵 [DEBUG] Cannot update track title: idx=${idx}, queue.length=${queue.length}`);
    }
    
    return result;
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

  shuffleBtn.onclick = async () => {
    // Regular random shuffle
    queue = [...tracks];
    shuffle(queue);
    console.log('🔀 Random shuffle applied to all tracks');
    
    // Save preference
    await savePlaylistPreference('shuffle');
    
    playIndex(0);
    // Update current track title after shuffle
    if (currentIndex >= 0 && currentIndex < queue.length) {
      const currentTrack = queue[currentIndex];
      updateCurrentTrackTitle(currentTrack);
    }
  };

  smartShuffleBtn.onclick = async ()=>{
     // Smart shuffle based on last play time (always same logic for all playlists)
     queue = smartShuffle([...tracks]);
     console.log('🧠 Smart shuffle applied (grouped by last play time)');
     
     // Save preference
     await savePlaylistPreference('smart');
     
     playIndex(0);
     // Update current track title after smart shuffle
     if (currentIndex >= 0 && currentIndex < queue.length) {
       const currentTrack = queue[currentIndex];
       updateCurrentTrackTitle(currentTrack);
     }
  };

  orderByDateBtn.onclick = async () => {
    // Sort tracks by YouTube publish date (oldest first)
    queue = orderByPublishDate([...tracks]);
    console.log('📅 Tracks ordered by YouTube publish date (oldest first)');
    
    // Save preference
    await savePlaylistPreference('order_by_date');
    
    playIndex(0);
    // Update current track title after ordering by date
    if (currentIndex >= 0 && currentIndex < queue.length) {
      const currentTrack = queue[currentIndex];
      updateCurrentTrackTitle(currentTrack);
    }
  };

  // Functions for control actions
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
    loadTrack,
    getCurrentIndex: () => currentIndex,
    setCurrentIndex: (newIdx) => { currentIndex = newIdx; }
  }, 'regular');

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
    const newSpeedIndex = await utilsCyclePlaybackSpeed(context, savePlaylistSpeed, 'regular');
    currentSpeedIndex = newSpeedIndex;
    updateSpeedDisplay(); // Update display after index is updated
  }

  // Initialize speed display
  updateSpeedDisplay();

  // Speed control button click handler
  if (cSpeed) {
    cSpeed.onclick = cyclePlaybackSpeed;
  }

  // Use the main togglePlayback function for consistency
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
  
  // syncRemoteState() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function syncRemoteState() {
    return await utilsSyncRemoteState('regular', { currentIndex, queue, media });
  }
  
  // pollRemoteCommands() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function pollRemoteCommands() {
    return await utilsPollRemoteCommands(executeRemoteCommand, false);
  }
  
  // executeRemoteCommand() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function executeRemoteCommand(command) {
    const context = {
      media, nextTrack, prevTrack, stopPlayback, togglePlayback, 
      isVolumeWheelActive, cVol, updateMuteIcon,
      syncRemoteState, syncLikeButtonsWithRemote
      // Кнопки больше не нужны - используется унифицированный getElementById
    };
    return await utilsExecuteRemoteCommand(command, context, 'regular');
  }
  
  // syncLikeButtonsWithRemote() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function syncLikeButtonsWithRemote() {
    return await utilsSyncLikeButtonsWithRemote();
  }
  
  // Setup remote control using centralized functions
  setupRemoteControlOverrides(playIndex, togglePlayback, syncRemoteState);
  setupRemoteControlInitialization(media, syncRemoteState, pollRemoteCommands, { currentIndex: () => currentIndex });
  
  // Initial render of the playlist after all functions are defined
  console.log('🎵 Initializing playlist render...');
  console.log('📊 Tracks loaded:', tracks.length);
  console.log('📊 Queue length:', queue.length);
  console.log('🎯 Current index:', currentIndex);
  
  if (tracks.length === 0) {
    console.warn('❌ No tracks loaded - check API endpoint');
  } else if (queue.length === 0) {
    console.warn('❌ Queue is empty - check playlist loading or shuffle function');
  } else {
    console.log('✅ Data looks good, rendering playlist...');
    console.log(`🎵 [DEBUG] Before renderList: tracks.length=${tracks.length}, queue.length=${queue.length}, currentIndex=${currentIndex}`);
    renderList();
    console.log('✅ Playlist rendered successfully');
    console.log(`🎵 [DEBUG] After renderList: currentIndex=${currentIndex}`);
    
    // Update speed display to show saved speed
    updateSpeedDisplay();
    console.log(`⚡ Speed display updated to show current speed: ${speedOptions[currentSpeedIndex]}x`);
    
    // Initialize current track title display
    if (currentIndex >= 0 && currentIndex < queue.length) {
      const currentTrack = queue[currentIndex];
      console.log(`🎵 [DEBUG] Initializing track title with track: ${currentTrack.name}`);
      updateCurrentTrackTitle(currentTrack);
      console.log('📝 Current track title display initialized');
      
      // Update track title width after initialization
      setTimeout(() => {
        if (typeof window.updateTrackTitleWidth === 'function') {
          window.updateTrackTitleWidth();
        }
      }, 200);
    } else {
      console.warn(`🎵 [DEBUG] Cannot initialize track title: currentIndex=${currentIndex}, queue.length=${queue.length}`);
    }
  }

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