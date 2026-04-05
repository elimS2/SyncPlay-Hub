// Импорт общих утилит из нового barrel файла
import { shuffle, smartShuffle, detectChannelGroup, smartChannelShuffle, getGroupPlaybackInfo, orderByPublishDate as utilsOrderByPublishDate, formatTime, updateSpeedDisplay as utilsUpdateSpeedDisplay, showNotification, handleVolumeWheel as utilsHandleVolumeWheel, stopTick as utilsStopTick, stopPlayback as utilsStopPlayback, playIndex as utilsPlayIndex, updateMuteIcon as utilsUpdateMuteIcon, nextTrack as utilsNextTrack, prevTrack as utilsPrevTrack, sendStreamEvent as utilsSendStreamEvent, startTick as utilsStartTick, reportEvent as utilsReportEvent, triggerAutoDeleteCheck as utilsTriggerAutoDeleteCheck, recordSeekEvent, saveVolumeToDatabase as utilsSaveVolumeToDatabase, loadSavedVolume as utilsLoadSavedVolume, performKeyboardSeek as utilsPerformKeyboardSeek, syncLikeButtonsWithRemote as utilsSyncLikeButtonsWithRemote, registerPlayerRemoteReactionSync as utilsRegisterPlayerRemoteReactionSync, togglePlayback as utilsTogglePlayback, showFsControls as utilsShowFsControls, updateFsVisibility as utilsUpdateFsVisibility, syncRemoteState as utilsSyncRemoteState, setupGlobalTooltip as utilsSetupGlobalTooltip, createTrackTooltipHTML, pollRemoteCommands as utilsPollRemoteCommands, cyclePlaybackSpeed as utilsCyclePlaybackSpeed, executeRemoteCommand as utilsExecuteRemoteCommand, deleteTrack as utilsDeleteTrack, initializeGoogleCastIntegration as utilsInitializeGoogleCastIntegration, castLoad as utilsCastLoad, loadTrack as utilsLoadTrack, setupMediaEndedHandler, setupMediaPlayPauseHandlers, setupMediaTimeUpdateHandler, setupMediaSeekedHandler, setupKeyboardHandler, setupProgressClickHandler, setupMediaSessionAPI, setupPlaylistToggleHandler, setupDeleteCurrentHandler, setupLikeDislikeHandlers, setupYouTubeHandler, setupFullscreenHandlers, setupSimpleControlHandlers, setupStreamHandler, setupBeforeUnloadHandler, setupAutoPlayInitialization, setupRemoteControlOverrides, setupRemoteControlInitialization, initializePlaylistPreferences, savePlaylistPreference as savePlaylistPreferenceModule, savePlaylistSpeed as savePlaylistSpeedModule, initializePlaylistLayoutManager, initializeTrackOrderManager, scrollActiveTrackToTop, ORDER_MODES, getCurrentOrderMode, getSmartBucketLabel, getSmartBucketSlug, renderTrackList } from '/static/js/modules/index.js';

// Импорт track title manager
import { updateCurrentTrackTitle } from '/static/js/modules/track-title-manager.js';
import { initMainPlayerPingPong } from '/static/js/modules/main-player-ping-pong.js';

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
  const playerA = document.getElementById('player');
  const playerB = document.getElementById('playerB');
  let media = playerA;
  const listElem = document.getElementById('tracklist');

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
  const playlistPanel = document.getElementById('playlistPanel');
  const controlBar = document.getElementById('controlBar');
  const customControls = document.getElementById('customControls');
  let fsTimer;
  const streamBtn = document.getElementById('streamBtn');
  let streamIdLeader = null;
  let tickTimer=null;

  // Playback speed control
  const speedOptions = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5];

  const playlistRel = typeof PLAYLIST_REL !== 'undefined' ? PLAYLIST_REL : '';
  let tracks = await fetchTracks(playlistRel);

  // Initialize playlist preferences using shared module
  const result = await initializePlaylistPreferences({
    relpath: playlistRel,
    playlistType: 'regular',
    tracks,
    speedOptions,
    shuffle,
    smartShuffle,
    orderByPublishDate
  });
  
  let { queue } = result;
  let { currentSpeedIndex } = result;

  // Wrapper functions for backward compatibility
  async function savePlaylistPreference(preference) {
    return await savePlaylistPreferenceModule(playlistRel, preference, 'regular');
  }

  async function savePlaylistSpeed(speed) {
    return await savePlaylistSpeedModule(playlistRel, speed, 'regular');
  }
  
  let currentIndex = -1;

  const pingPong = initMainPlayerPingPong({
    playerA,
    playerB,
    wrapper,
    queue,
    getCurrentIndex: () => currentIndex,
    getActiveMedia: () => media,
    setActiveMedia: (el) => {
      media = el;
    },
    getVolume: () => parseFloat(cVol.value) || 0,
  });
  
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
    const orderMode = (typeof getCurrentOrderMode === 'function') ? getCurrentOrderMode() : null;
    const isSmart = orderMode === ORDER_MODES.SMART_SHUFFLE;

    renderTrackList({
      listElem,
      queue,
      currentIndex,
      isSmart,
      getBucketLabel: getSmartBucketLabel,
      getBucketSlug: getSmartBucketSlug,
      createTrackTooltipHTML,
      onPlayIndex: (idx) => playIndex(idx),
      createDeleteButton: (t, idx) => {
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'delete-btn';
        deleteBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c0 1 1 2 1 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>';
        deleteBtn.title = `Delete track: ${t.name.replace(/\s*\[.*?\]$/, '')} (${t.video_id})`;
        deleteBtn.style.cssText = 'background: none; border: none; color: #ff4444; cursor: pointer; font-size: 16px; padding: 4px 8px; border-radius: 4px; margin-left: 8px; opacity: 0.7; transition: opacity 0.2s ease, background-color 0.2s ease;';
        deleteBtn.onmouseenter = () => { deleteBtn.style.opacity = '1'; deleteBtn.style.backgroundColor = 'rgba(255, 68, 68, 0.1)'; };
        deleteBtn.onmouseleave = () => { deleteBtn.style.opacity = '0.7'; deleteBtn.style.backgroundColor = 'transparent'; };
        deleteBtn.onclick = (e) => { e.stopPropagation(); deleteTrack(t, idx); };
        return deleteBtn;
      }
    });
    
    // Update current track title display after rendering list
    if (currentIndex >= 0 && currentIndex < queue.length) {
      const currentTrack = queue[currentIndex];
      updateCurrentTrackTitle(currentTrack);
    }
    
    // Update delete button tooltip
    const deleteCurrentBtn = document.getElementById('deleteCurrentBtn');
    if (deleteCurrentBtn && deleteCurrentBtn.updateTooltip) {
      deleteCurrentBtn.updateTooltip();
    }
    
    // Create global tooltip system
    setupGlobalTooltip();

    // Auto-scroll is handled centrally inside utilsLoadTrack() after renderList()
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
        getMedia: () => media,
        media,
        speedOptions, currentSpeedIndex, castLoad, renderList,
        cLike, cDislike, reportEvent, sendStreamEvent,
        syncRemoteStateAfterReaction: syncRemoteState,
        syncRemoteStateImmediate: () => syncRemoteState(),
    });
    
    // Update track title display
    if (idx >= 0 && idx < queue.length) {
      console.log(`🎵 [DEBUG] Updating track title for track: ${queue[idx].name}`);
      updateCurrentTrackTitle(queue[idx]);
    } else {
      console.warn(`🎵 [DEBUG] Cannot update track title: idx=${idx}, queue.length=${queue.length}`);
    }
    
    // Update delete button tooltip
    const deleteCurrentBtn = document.getElementById('deleteCurrentBtn');
    if (deleteCurrentBtn && deleteCurrentBtn.updateTooltip) {
      deleteCurrentBtn.updateTooltip();
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
    playIndex,
    tryStitchToNextTrack: (next) => pingPong.tryStitchToNextTrack(next),
    additionalEndedElements: playerB ? [playerB] : [],
  });

  // Initialize track order manager
  await initializeTrackOrderManager({
    tracks,
    shuffle,
    smartShuffle,
    orderByPublishDate,
    playIndex,
    updateCurrentTrackTitle,
    relpath: playlistRel,
    playlistType: 'regular',
    getCurrentIndex: () => currentIndex,
    getQueue: () => queue,  // Add function to get current queue
    setQueue: (newQueue) => { queue = newQueue; },
    showNotification
  });

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
    queue: () => queue,  // Pass as function to always get current queue
    tracks,
    media,
    getMedia: () => media,
    playIndex,
    renderList,
    showNotification,
    loadTrack,
    getCurrentIndex: () => currentIndex,
    setCurrentIndex: (newIdx) => { currentIndex = newIdx; },
    // Add function to update global queue
    updateQueue: (newQueue) => { 
      queue.length = 0; 
      queue.push(...newQueue); 
    }
  }, 'regular');

  // Setup fullscreen and control handlers using centralized functions
  setupFullscreenHandlers(fullBtn, cFull, wrapper);
  setupSimpleControlHandlers(cPrev, cNext, media, prevTrack, nextTrack, togglePlayback, playerB ? [playerB] : []);

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
    currentIndex: () => currentIndex,
    reportEvent,
    getMedia: () => media,
    pingPongMediaElements: playerB ? [playerB] : [],
  });

  // formatTime() теперь импортируется из player-utils.js

  // Setup media timeupdate handler using centralized function
  setupMediaTimeUpdateHandler(media, {
    progressBar,
    timeLabel,
    formatTime,
    getMedia: () => media,
    pingPongMediaElements: playerB ? [playerB] : [],
  });

  // Track seek events
  let lastSeekPosition = null;
  const seekState = { seekStartPosition: null };
  
  // Setup progress container click handler using centralized function
  setupProgressClickHandler(progressContainer, media, {
    currentIndex: () => currentIndex,
    sendStreamEvent,
    seekState,
    getMedia: () => media,
  });
  
  // Setup media seeked handler using centralized function
  setupMediaSeekedHandler(media, {
    queue,
    currentIndex: () => currentIndex,
    recordSeekEvent,
    seekState,
    getMedia: () => media,
    pingPongMediaElements: playerB ? [playerB] : [],
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
    media,
    getMedia: () => media,
  });

  // media click handler теперь обрабатывается в setupSimpleControlHandlers()

  async function syncRemoteState(opts) {
    return await utilsSyncRemoteState('regular', { currentIndex, queue, media }, opts);
  }
  utilsRegisterPlayerRemoteReactionSync(syncRemoteState);

  // Setup like/dislike and YouTube handlers using centralized functions
  setupLikeDislikeHandlers(cLike, cDislike, {
    currentIndex: () => currentIndex,
    queue: () => queue,  // Pass as function to always get current queue
    media,
    getMedia: () => media,
    reportEvent,
    likedCurrent
  });
  
  setupYouTubeHandler(cYoutube, {
    currentIndex: () => currentIndex,
    queue: () => queue  // Pass as function to always get current queue
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
      syncRemoteState
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
  setupRemoteControlInitialization(media, syncRemoteState, pollRemoteCommands, {
    currentIndex: () => currentIndex,
    getMedia: () => media,
    pingPongMediaElements: playerB ? [playerB] : [],
  });
  
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
      queue, tracks, media, getMedia: () => media, playIndex, renderList,
      showNotification, loadTrack,
      currentIndex: () => currentIndex,
      getCurrentIndex: () => currentIndex,
      setCurrentIndex: (newIdx) => { currentIndex = newIdx; },
      // Add function to update global queue
      updateQueue: (newQueue) => { 
        queue.length = 0; 
        queue.push(...newQueue); 
      }
    };
    return await utilsDeleteTrack(track, trackIndex, context); // Используется универсальная логика с file locks
  }

  // showNotification() теперь импортируется из player-utils.js

  setInterval(async () => {
    if (typeof syncLikeButtonsWithRemote === 'function') {
      await syncLikeButtonsWithRemote();
    }
  }, 3000);
  
  window.loadTrack = loadTrack;

  // ==============================
  // PLAYLIST LAYOUT MANAGER
  // ==============================
  
  // Initialize playlist layout manager for regular player
  await initializePlaylistLayoutManager({
    relpath: playlistRel,
    playlistType: 'regular'
  });

})(); 