// Barrel file for player utilities - re-exports all public APIs
// This provides backward compatibility during the refactoring transition

// Re-export from playlist-utils.js
export { 
    shuffle, 
    smartShuffle, 
    smartChannelShuffle, 
    getGroupPlaybackInfo, 
    detectChannelGroup, 
    orderByPublishDate, 
    triggerAutoDeleteCheck, 
    loadTrack 
} from './player/playlist-utils.js';

// Re-export from time-format.js
export { formatTime } from './time-format.js';

// Re-export from ui-effects.js
export { 
    updateSpeedDisplay, 
    showNotification, 
    showFsControls, 
    updateFsVisibility, 
    createTrackTooltipHTML, 
    setupGlobalTooltip 
} from './ui-effects.js';

// Re-export from controls.js
export { 
    handleVolumeWheel, 
    stopTick, 
    stopPlayback, 
    playIndex, 
    updateMuteIcon, 
    nextTrack, 
    prevTrack, 
    startTick, 
    performKeyboardSeek, 
    syncLikeButtonsWithRemote, 
    syncLikesAfterAction, 
    setupLikeSyncHandlers, 
    togglePlayback, 
    cyclePlaybackSpeed, 
    deleteTrack, 
    initializeGoogleCastIntegration, 
    castLoad, 
    setupMediaEndedHandler, 
    setupMediaPlayPauseHandlers, 
    setupMediaTimeUpdateHandler, 
    setupMediaSeekedHandler, 
    setupKeyboardHandler, 
    setupProgressClickHandler, 
    setupMediaSessionAPI, 
    setupPlaylistToggleHandler, 
    setupDeleteCurrentHandler, 
    setupLikeDislikeHandlers, 
    setupYouTubeHandler, 
    setupFullscreenHandlers, 
    setupSimpleControlHandlers, 
    executeDeleteWithoutConfirmation, 
    setupStreamHandler, 
    setupBeforeUnloadHandler, 
    setupAutoPlayInitialization, 
    setupRemoteControlOverrides, 
    setupRemoteControlInitialization 
} from './controls.js';

// Re-export from player-state.js
export { 
    saveVolumeToDatabase, 
    loadSavedVolume, 
    syncRemoteState 
} from './player-state.js';

// Re-export from dom-utils.js
export { formatFileSize } from './dom-utils.js';

// Re-export from event-bus.js
export { 
    sendStreamEvent, 
    reportEvent, 
    recordSeekEvent, 
    pollRemoteCommands, 
    executeRemoteCommand 
} from './event-bus.js';

// Re-export from playlist-preferences.js
export {
    savePlaylistPreference,
    savePlaylistSpeed,
    loadPlaylistSpeed,
    loadPlaylistPreference,
    applyDisplayPreference,
    initializePlaylistPreferences,
    setupSortButtonHandlers
} from './playlist-preferences.js';

// Re-export from error-handler.js
export { 
    logError, 
    showErrorToast, 
    withErrorHandling 
} from './error-handler.js';

// Re-export from adaptive-layout.js
export {
    shouldShowPlaylistUnderVideo,
    applyAdaptivePlaylistLayout,
    setupAdaptiveLayout,
    initializeAdaptiveLayout
} from './adaptive-layout.js';

// Re-export from playlist-layout-manager.js
export {
  LAYOUT_MODES,
  applyLayoutMode,
  cycleLayoutMode,
  getCurrentLayoutMode,
  setupLayoutToggleButton,
  initializePlaylistLayoutManager
} from './playlist-layout-manager.js';

// Re-export from track-order-manager.js
export {
  ORDER_MODES,
  applyOrderMode,
  cycleOrderMode,
  getCurrentOrderMode,
  setupOrderToggleButton,
  initializeTrackOrderManager
} from './track-order-manager.js';

// Legacy compatibility - re-export everything from the original player-utils.js
// This ensures existing imports continue to work during the transition
export * from './player-utils.js'; 