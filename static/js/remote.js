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

// Wake Lock state will be managed by keep-awake module

// ==============================
// MODULE IMPORTS & SETUP
// ==============================

// Toast notifications will be loaded from modules

// Volume control functions will be loaded from modules

// Keep awake functions will be loaded from modules

// Remote control class will be loaded from modules

// Load modules dynamically (for browser environment)
async function loadModules() {
  try {
    // Toast notifications module will be available via window.ToastNotifications
    
    // Volume control module will be available via window.VolumeControl
    
    // Keep awake module will be available via window.KeepAwake
    
    // Remote control module will be available via window.RemoteControl
    
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
  
  // Toast functions are now available via window.ToastNotifications
  
  // Initialize core remote control
  if (window.RemoteControl) {
    console.log('📱 Initializing Remote Control...');
    const remoteControl = new window.RemoteControl();
    
    // Store reference for cross-module communication
    document.querySelector('.remote-container').remoteControlInstance = remoteControl;
    window.remoteControlInstance = remoteControl; // Global reference
    
    console.log('📱 Remote Control initialized');
  } else {
    console.error('📱 RemoteControl class not available');
  }
  
  // Initialize keep awake system early for immediate screen protection
  if (window.KeepAwake && window.KeepAwake.initKeepAwakeHandlers) {
    console.log('📱 Initializing Keep Awake handlers...');
    console.log('📱 Available Keep Awake methods:', Object.keys(window.KeepAwake));
    window.KeepAwake.initKeepAwakeHandlers();
    console.log('📱 Keep Awake handlers initialized');
  } else {
    console.warn('📱 Keep Awake module not available');
    console.warn('📱 window.KeepAwake:', window.KeepAwake);
  }
  
  // Initialize hardware volume control last
  if (window.VolumeControl && window.VolumeControl.initHardwareVolumeControl) {
    console.log('📱 Initializing Hardware Volume Control...');
    window.VolumeControl.initHardwareVolumeControl();
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
  SERVER_PORT
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