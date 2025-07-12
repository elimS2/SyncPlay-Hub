/**
 * Remote Control Main Entry Point
 * Coordinates all remote control modules and handles initialization
 */

// ==============================
// GLOBAL CONFIGURATION
// ==============================

// Server configuration
const SERVER_IP = window.SERVER_IP || "localhost";
const SERVER_PORT = window.SERVER_PORT || "8000";

// Wake Lock state management (shared across modules)
let wakeLock = null;
let wakeLockSupported = false;
let keepAwakeMethod = 'none';
let keepAwakeActive = false;
let keepAwakeInterval = null;
let hiddenVideo = null;
let webRTCConnection = null;

// ==============================
// MODULE IMPORTS & SETUP
// ==============================

// Toast notifications must be available globally for other modules
let showVolumeToast, showKeepAwakeToast, showToast;

// Volume control functions
let initHardwareVolumeControl, adjustVolume;

// Keep awake functions
let requestWakeLock, initKeepAwakeHandlers;

// Core remote control class
let RemoteControl;

// Load modules dynamically (for browser environment)
async function loadModules() {
  try {
    // Import toast notifications module
    if (typeof window.ToastNotifications !== 'undefined') {
      ({ showVolumeToast, showKeepAwakeToast, showToast } = window.ToastNotifications);
    }
    
    // Import volume control module
    if (typeof window.VolumeControl !== 'undefined') {
      ({ initHardwareVolumeControl, adjustVolume } = window.VolumeControl);
    }
    
    // Import keep awake module
    if (typeof window.KeepAwake !== 'undefined') {
      ({ requestWakeLock, initKeepAwakeHandlers } = window.KeepAwake);
    }
    
    // Import remote control module
    if (typeof window.RemoteControl !== 'undefined') {
      RemoteControl = window.RemoteControl;
    }
    
    console.log('📱 All modules loaded successfully');
    return true;
  } catch (error) {
    console.error('📱 Error loading modules:', error);
    return false;
  }
}

// ==============================
// MAIN INITIALIZATION
// ==============================

document.addEventListener('DOMContentLoaded', async () => {
  console.log('📱 Remote Control: Initializing...');
  
  // Load all modules first
  const modulesLoaded = await loadModules();
  if (!modulesLoaded) {
    console.error('📱 Failed to load modules, falling back to basic functionality');
    return;
  }
  
  // Make toast functions globally available for cross-module usage
  if (showVolumeToast) window.showVolumeToast = showVolumeToast;
  if (showKeepAwakeToast) window.showKeepAwakeToast = showKeepAwakeToast;
  if (showToast) window.showToast = showToast;
  
  // Initialize core remote control
  if (RemoteControl) {
    console.log('📱 Initializing Remote Control...');
    const remoteControl = new RemoteControl();
    
    // Store reference for cross-module communication
    document.querySelector('.remote-container').remoteControlInstance = remoteControl;
    window.remoteControlInstance = remoteControl; // Global reference
    
    console.log('📱 Remote Control initialized');
  } else {
    console.error('📱 RemoteControl class not available');
  }
  
  // Initialize keep awake system early for immediate screen protection
  if (initKeepAwakeHandlers) {
    console.log('📱 Initializing Keep Awake handlers...');
    initKeepAwakeHandlers();
    console.log('📱 Keep Awake handlers initialized');
  } else {
    console.warn('📱 Keep Awake module not available');
  }
  
  // Initialize hardware volume control last
  if (initHardwareVolumeControl) {
    console.log('📱 Initializing Hardware Volume Control...');
    initHardwareVolumeControl();
    console.log('📱 Hardware Volume Control initialized');
  } else {
    console.warn('📱 Volume Control module not available');
  }
  
  console.log('📱 Remote Control: Fully initialized!');
});

// ==============================
// GLOBAL UTILITIES
// ==============================

// Export global configuration for modules
window.REMOTE_CONFIG = {
  SERVER_IP,
  SERVER_PORT,
  // Wake Lock state (for keep-awake module coordination)
  getWakeLockState: () => ({
    wakeLock,
    wakeLockSupported,
    keepAwakeMethod,
    keepAwakeActive,
    keepAwakeInterval,
    hiddenVideo,
    webRTCConnection
  }),
  setWakeLockState: (state) => {
    if (state.wakeLock !== undefined) wakeLock = state.wakeLock;
    if (state.wakeLockSupported !== undefined) wakeLockSupported = state.wakeLockSupported;
    if (state.keepAwakeMethod !== undefined) keepAwakeMethod = state.keepAwakeMethod;
    if (state.keepAwakeActive !== undefined) keepAwakeActive = state.keepAwakeActive;
    if (state.keepAwakeInterval !== undefined) keepAwakeInterval = state.keepAwakeInterval;
    if (state.hiddenVideo !== undefined) hiddenVideo = state.hiddenVideo;
    if (state.webRTCConnection !== undefined) webRTCConnection = state.webRTCConnection;
  }
};

// ==============================
// ERROR HANDLING & FALLBACKS
// ==============================

// Global error handler for remote control
window.addEventListener('error', (event) => {
  console.error('📱 Remote Control Error:', event.error);
});

// Handle unhandled promise rejections
window.addEventListener('unhandledrejection', (event) => {
  console.error('📱 Remote Control Promise Rejection:', event.reason);
  event.preventDefault(); // Prevent console spam
});

console.log('📱 Remote Control: Main script loaded'); 