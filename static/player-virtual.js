import { shuffle, smartShuffle, detectChannelGroup, smartChannelShuffle, getGroupPlaybackInfo, orderByPublishDate as utilsOrderByPublishDate, formatTime, updateSpeedDisplay as utilsUpdateSpeedDisplay, showNotification, handleVolumeWheel as utilsHandleVolumeWheel, stopTick as utilsStopTick, stopPlayback as utilsStopPlayback, playIndex as utilsPlayIndex, updateMuteIcon as utilsUpdateMuteIcon, nextTrack as utilsNextTrack, prevTrack as utilsPrevTrack, sendStreamEvent as utilsSendStreamEvent, startTick as utilsStartTick, reportEvent as utilsReportEvent, triggerAutoDeleteCheck as utilsTriggerAutoDeleteCheck, recordSeekEvent, saveVolumeToDatabase as utilsSaveVolumeToDatabase, loadSavedVolume as utilsLoadSavedVolume, performKeyboardSeek as utilsPerformKeyboardSeek, syncLikeButtonsWithRemote as utilsSyncLikeButtonsWithRemote, registerPlayerRemoteReactionSync as utilsRegisterPlayerRemoteReactionSync, togglePlayback as utilsTogglePlayback, showFsControls as utilsShowFsControls, updateFsVisibility as utilsUpdateFsVisibility, syncRemoteState as utilsSyncRemoteState, setupGlobalTooltip as utilsSetupGlobalTooltip, createTrackTooltipHTML, pollRemoteCommands as utilsPollRemoteCommands, cyclePlaybackSpeed as utilsCyclePlaybackSpeed, executeRemoteCommand as utilsExecuteRemoteCommand, deleteTrack as utilsDeleteTrack, initializeGoogleCastIntegration as utilsInitializeGoogleCastIntegration, castLoad as utilsCastLoad, loadTrack as utilsLoadTrack, setupMediaEndedHandler, setupMediaPlayPauseHandlers, setupMediaTimeUpdateHandler, setupMediaSeekedHandler, setupKeyboardHandler, setupProgressClickHandler, setupMediaSessionAPI, setupPlaylistToggleHandler, setupDeleteCurrentHandler, setupLikeDislikeHandlers, setupYouTubeHandler, setupFullscreenHandlers, setupSimpleControlHandlers, setupStreamHandler, setupBeforeUnloadHandler, setupAutoPlayInitialization, setupRemoteControlOverrides, setupRemoteControlInitialization, initializePlaylistPreferences, savePlaylistPreference as savePlaylistPreferenceModule, savePlaylistSpeed as savePlaylistSpeedModule, initializePlaylistLayoutManager, initializeTrackOrderManager, ORDER_MODES, getCurrentOrderMode, getSmartBucketLabel, getSmartBucketSlug, renderTrackList } from '/static/js/modules/index.js';

import { updateCurrentTrackTitle } from '/static/js/modules/track-title-manager.js';
import { initMainPlayerPingPong } from '/static/js/modules/main-player-ping-pong.js';

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

function orderByPublishDate(tracks) {
  return utilsOrderByPublishDate(tracks, 'regular');
}

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

  // Get virtual playlist identifier
  const likeCount = typeof VIRTUAL_PLAYLIST_LIKE_COUNT !== 'undefined' ? VIRTUAL_PLAYLIST_LIKE_COUNT : 1;
  const virtualRelpath = `virtual_${likeCount}_likes`;

  // Initialize playlist preferences using shared module
  const result = await initializePlaylistPreferences({
    relpath: virtualRelpath,
    playlistType: 'virtual',
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
    return await savePlaylistPreferenceModule(virtualRelpath, preference, 'virtual');
  }

  async function savePlaylistSpeed(speed) {
    return await savePlaylistSpeedModule(virtualRelpath, speed, 'virtual');
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
  
  console.log('🧠 Applied smart shuffle for virtual playlist (grouped by last play time)');

  if (tracks.length === 0) {
    console.warn('❌ No tracks loaded - check API endpoint');
  } else if (queue.length === 0) {
    console.warn('❌ Queue is empty - check playlist loading or shuffle function');
  } else {
    console.log('✅ Data looks good, rendering playlist...');
    renderList();
    console.log('✅ Playlist rendered successfully');
    
    // Update track title after initial render
    if (currentIndex >= 0 && currentIndex < queue.length) {
      updateCurrentTrackTitle(queue[currentIndex]);
    }
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

    console.log(`🎵 Rendered ${queue.length} tracks in playlist`);
    const deleteCurrentBtn = document.getElementById('deleteCurrentBtn');
    if (deleteCurrentBtn && deleteCurrentBtn.updateTooltip) {
      deleteCurrentBtn.updateTooltip();
    }
    setupGlobalTooltip();
  }

  function loadTrack(idx, autoplay=false){
    const result = utilsLoadTrack(idx, autoplay, {
        queue, currentIndex, setCurrentIndex: (newIdx) => { currentIndex = newIdx; },
        getMedia: () => media,
        media,
        speedOptions, currentSpeedIndex, castLoad, renderList,
        cLike, cDislike, reportEvent, sendStreamEvent,
        syncRemoteStateAfterReaction: syncRemoteState,
        syncRemoteStateImmediate: () => syncRemoteState(),
    });
    
    // Update track title display
    if (idx >= 0 && idx < queue.length) {
      updateCurrentTrackTitle(queue[idx]);
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
    relpath: virtualRelpath,
    playlistType: 'virtual',
    getCurrentIndex: () => currentIndex,
    getQueue: () => queue,  // Add function to get current queue
    setQueue: (newQueue) => { queue = newQueue; },
    showNotification
  });

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
      console.log(`🔍 [Delete] Updating global queue: old length=${queue.length}, new length=${newQueue.length}`);
      queue.length = 0; 
      queue.push(...newQueue); 
      console.log(`🔍 [Delete] Global queue updated successfully, new length: ${queue.length}`);
    }
  }, 'virtual');

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
    const newSpeedIndex = await utilsCyclePlaybackSpeed(context, savePlaylistSpeed, 'virtual');
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
    return await utilsSyncRemoteState('virtual', { currentIndex, queue, media }, opts);
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
  
  console.log('🔍 [DEBUG] About to start remote control setup...');

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
      syncRemoteState
    };
    return await utilsExecuteRemoteCommand(command, context, 'virtual');
  }
  
  // syncLikeButtonsWithRemote() теперь импортируется из player-utils.js
  // Wrapper function для совместимости с существующим кодом
  async function syncLikeButtonsWithRemote() {
    const vid =
      currentIndex >= 0 && currentIndex < queue.length ? queue[currentIndex]?.video_id : null;
    return await utilsSyncLikeButtonsWithRemote(vid);
  }
  
  // Setup remote control using centralized functions  
  setupRemoteControlOverrides(playIndex, togglePlayback, syncRemoteState);
  setupRemoteControlInitialization(media, syncRemoteState, pollRemoteCommands, {
    currentIndex: () => currentIndex,
    getMedia: () => media,
    pingPongMediaElements: playerB ? [playerB] : [],
  });
  
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
        console.log(`🔍 [Delete] Updating global queue: old length=${queue.length}, new length=${newQueue.length}`);
        queue.length = 0; 
        queue.push(...newQueue); 
        console.log(`🔍 [Delete] Global queue updated successfully, new length: ${queue.length}`);
      }
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
  
  setInterval(async () => {
    if (typeof syncLikeButtonsWithRemote === 'function') {
      await syncLikeButtonsWithRemote();
    }
  }, 3000);
  
  window.loadTrack = loadTrack;

  // ==============================
  // PLAYLIST LAYOUT MANAGER
  // ==============================
  
  // Initialize playlist layout manager for virtual player
  await initializePlaylistLayoutManager({
    relpath: virtualRelpath,
    playlistType: 'virtual'
  });

  })(); 