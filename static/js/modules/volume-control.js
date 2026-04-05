/**
 * Volume Control Module
 * Handles hardware volume buttons and volume adjustments on the remote page
 */

// Import toast notifications (use global reference)
function getShowVolumeToast() {
  return window.showVolumeToast || (window.ToastNotifications && window.ToastNotifications.showVolumeToast) || null;
}

// Hardware volume buttons control
function initHardwareVolumeControl() {
  console.log('📱 Initializing hardware volume control...');
  
  // Detect Android
  const isAndroid = /Android/i.test(navigator.userAgent);
  console.log('📱 Android detected:', isAndroid);
  
  // Multiple approaches for volume control
  document.addEventListener('keydown', handleVolumeKeys, { passive: false });
  document.addEventListener('keyup', handleVolumeKeys, { passive: false });
  
  // Android-specific volume handling
  if (isAndroid) {
    console.log('📱 Setting up Android-specific volume control...');
    
    // Try to create a hidden audio element to capture volume events
    const audioElement = document.createElement('audio');
    audioElement.muted = true;
    audioElement.loop = true;
    audioElement.volume = 0.5;
    audioElement.style.display = 'none';
    
    // Use a silent audio file or data URL
    audioElement.src = 'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmYdCEOZ2+/Eeyw';
    audioElement.preload = 'auto';
    
    document.body.appendChild(audioElement);
    
    // Try to play the silent audio to enable volume control
    audioElement.play().then(() => {
      console.log('📱 Silent audio playing for Android volume control');
      
      // Listen for volume change events
      audioElement.addEventListener('volumechange', () => {
        console.log('📱 Audio volume changed:', audioElement.volume);
      });
      
    }).catch(error => {
      console.log('📱 Silent audio play failed:', error);
    });
  }
  
  // Media Session API for hardware buttons
  if ('mediaSession' in navigator) {
    console.log('📱 Media Session API available');
    
    // Set up media session metadata
    navigator.mediaSession.metadata = new MediaMetadata({
      title: 'SyncPlay-Hub Remote',
      artist: 'Remote Control',
      artwork: [
        { src: '/static/favicon.ico', sizes: '96x96', type: 'image/x-icon' }
      ]
    });
    
    // Handle volume control via media session
    try {
      navigator.mediaSession.setActionHandler('seekbackward', () => {
        adjustVolume(-0.01);
        console.log('📱 Media Session: Volume down');
      });
      
      navigator.mediaSession.setActionHandler('seekforward', () => {
        adjustVolume(0.01);
        console.log('📱 Media Session: Volume up');
      });
      
      // Also try previoustrack/nexttrack for volume
      navigator.mediaSession.setActionHandler('previoustrack', () => {
        adjustVolume(-0.01);
        console.log('📱 Media Session: Previous (Volume down)');
      });
      
      navigator.mediaSession.setActionHandler('nexttrack', () => {
        adjustVolume(0.01);
        console.log('📱 Media Session: Next (Volume up)');
      });
        
      console.log('📱 Media Session volume handlers set');
    } catch (error) {
      console.log('📱 Media Session volume handlers not supported:', error);
    }
  }
  
  // Add visual instructions for Android users
  if (isAndroid) {
    addAndroidInstructions();
  }
}

function addAndroidInstructions() {
  // Add a small instruction tooltip
  const instructionDiv = document.createElement('div');
  instructionDiv.style.cssText = `
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0, 0, 0, 0.8);
    color: white;
    padding: 10px 15px;
    border-radius: 8px;
    font-size: 12px;
    z-index: 1000;
    text-align: center;
    backdrop-filter: blur(10px);
  `;
  instructionDiv.innerHTML = 'Use the volume slider or hardware volume buttons';
  
  document.body.appendChild(instructionDiv);
  
  // Auto-hide after 5 seconds
  setTimeout(() => {
    instructionDiv.style.opacity = '0';
    instructionDiv.style.transition = 'opacity 0.5s ease';
    setTimeout(() => instructionDiv.remove(), 500);
  }, 5000);
}

function handleVolumeKeys(event) {
  // Handle hardware volume keys (Android/some browsers)
  const volumeKeys = [
    'VolumeUp', 'VolumeDown',           // Standard
    'AudioVolumeUp', 'AudioVolumeDown', // Some Android browsers
    'MediaVolumeUp', 'MediaVolumeDown'  // Alternative names
  ];
  
  if (volumeKeys.includes(event.code) || volumeKeys.includes(event.key)) {
    event.preventDefault();
    event.stopPropagation();
    
    const isVolumeUp = event.code?.includes('Up') || event.key?.includes('Up');
    adjustVolume(isVolumeUp ? 0.01 : -0.01);
    
    console.log('📱 Hardware volume', isVolumeUp ? 'up' : 'down', 'pressed');
    return false;
  }
  
  // Also handle arrow keys as fallback
  if (event.code === 'ArrowUp' && event.altKey) {
    event.preventDefault();
    adjustVolume(0.01);
    console.log('📱 Alt+Up volume control');
  } else if (event.code === 'ArrowDown' && event.altKey) {
    event.preventDefault();
    adjustVolume(-0.01);
    console.log('📱 Alt+Down volume control');
  }
}

function adjustVolume(delta) {
  const volumeSlider = document.getElementById('volumeSlider');
  const volumeValue = document.getElementById('volumeValue');
  
  if (!volumeSlider) return;
  
  let currentVolume = parseInt(volumeSlider.value);
  let newVolume = Math.max(0, Math.min(100, currentVolume + (delta * 100)));
  
  // Update UI
  volumeSlider.value = newVolume;
  volumeValue.textContent = newVolume + '%';
  
  // Activate volume control protection
  const remoteControl = document.querySelector('.remote-container').remoteControlInstance;
  if (remoteControl) {
    remoteControl.setVolumeControlActive();
  }
  
  // Prepare payload with track info
  const payload = { volume: newVolume / 100 };
  if (remoteControl && remoteControl.currentStatus && remoteControl.currentStatus.current_track) {
    payload.video_id = remoteControl.currentStatus.current_track.video_id;
    payload.position = remoteControl.currentStatus.progress;
  }
  
  // Send to server
  fetch('/api/remote/volume', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  
  // Show volume feedback
      const toast = getShowVolumeToast();
    if (toast) toast(newVolume);
  
  console.log('📱 Volume adjusted to:', newVolume + '%');
}

// Export functions for browser environment
window.VolumeControl = {
  initHardwareVolumeControl,
  addAndroidInstructions,
  handleVolumeKeys,
  adjustVolume
}; 