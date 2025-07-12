// Remote control client functionality
const SERVER_IP = window.SERVER_IP || "localhost";
const SERVER_PORT = window.SERVER_PORT || "8000";

// Wake Lock state management
let wakeLock = null;
let wakeLockSupported = false;
let keepAwakeMethod = 'none';
let keepAwakeActive = false;
let keepAwakeInterval = null;
let hiddenVideo = null;
let webRTCConnection = null;

class RemoteControl {
  constructor() {
    this.connected = false;
    this.currentTrack = null;
    this.currentStatus = null;
    this.syncInterval = null;
    this.isVolumeControlActive = false;
    this.volumeControlTimeout = null;
    
    this.initElements();
    this.attachEvents();
    this.startSync();
  }
  
  initElements() {
    // Status elements
    this.statusDot = document.getElementById('statusDot');
    this.statusText = document.getElementById('statusText');
    
    // Player type elements
    this.playerTypeInfo = document.getElementById('playerTypeInfo');
    this.playerTypeText = document.getElementById('playerTypeText');
    
    // Track info elements
    this.trackTitle = document.getElementById('trackTitle');
    this.trackStatus = document.getElementById('trackStatus');
    this.progressBar = document.getElementById('progressBar');
    this.currentTime = document.getElementById('currentTime');
    this.totalTime = document.getElementById('totalTime');
    
    // Control buttons
    this.prevBtn = document.getElementById('prevBtn');
    this.playBtn = document.getElementById('playBtn');
    this.nextBtn = document.getElementById('nextBtn');
    this.shuffleBtn = document.getElementById('shuffleBtn');
    this.likeBtn = document.getElementById('likeBtn');
    this.dislikeBtn = document.getElementById('dislikeBtn');
    this.youtubeBtn = document.getElementById('youtubeBtn');
    this.stopBtn = document.getElementById('stopBtn');
    this.fullscreenBtn = document.getElementById('fullscreenBtn');
    
    // Volume controls
    this.volumeSlider = document.getElementById('volumeSlider');
    this.volumeValue = document.getElementById('volumeValue');
    this.volumeUpBtn = document.getElementById('volumeUpBtn');
    this.volumeDownBtn = document.getElementById('volumeDownBtn');
    
    // Info elements
    this.serverInfo = document.getElementById('serverInfo');
    this.lastSync = document.getElementById('lastSync');
  }
  
  attachEvents() {
    // Control buttons
    this.prevBtn.addEventListener('click', () => this.sendCommand('prev'));
    this.playBtn.addEventListener('click', () => this.sendCommand('play'));
    this.nextBtn.addEventListener('click', () => this.sendCommand('next'));
    this.shuffleBtn.addEventListener('click', () => this.sendCommand('shuffle'));
    this.likeBtn.addEventListener('click', async () => {
      // Send command and wait for sync (no immediate toggle)
      await this.sendCommand('like');
      
      // Sync likes after action with longer delay to allow processing
      if (this.currentStatus && this.currentStatus.current_track && this.currentStatus.current_track.video_id) {
        await this.syncLikesAfterAction(this.currentStatus.current_track.video_id, 'like');
      }
    });
    this.dislikeBtn.addEventListener('click', async () => {
      // Send command and wait for sync (no immediate toggle)
      await this.sendCommand('dislike');
      
      // Sync likes after action with longer delay to allow processing
      if (this.currentStatus && this.currentStatus.current_track && this.currentStatus.current_track.video_id) {
        await this.syncLikesAfterAction(this.currentStatus.current_track.video_id, 'dislike');
      }
    });
    this.youtubeBtn.addEventListener('click', () => this.sendCommand('youtube'));
    this.stopBtn.addEventListener('click', () => this.sendCommand('stop'));
    this.fullscreenBtn.addEventListener('click', () => this.sendCommand('fullscreen'));
    
    // Volume slider
    this.volumeSlider.addEventListener('input', (e) => {
      const volume = parseInt(e.target.value);
      this.volumeValue.textContent = volume + '%';
      
      // Activate volume control protection
      this.setVolumeControlActive();
      
      // Add track info for volume logging
      const payload = { volume: volume / 100 };
      if (this.currentStatus && this.currentStatus.current_track) {
        payload.video_id = this.currentStatus.current_track.video_id;
        payload.position = this.currentStatus.progress;
      }
      
      this.sendCommand('volume', payload);
    });

    // Volume buttons
    this.volumeUpBtn.addEventListener('click', () => {
      const currentVolume = parseInt(this.volumeSlider.value);
      const newVolume = Math.min(100, currentVolume + 1);
      this.volumeSlider.value = newVolume;
      this.volumeValue.textContent = newVolume + '%';
      
      // Activate volume control protection
      this.setVolumeControlActive();
      
      // Add track info for volume logging
      const payload = { volume: newVolume / 100 };
      if (this.currentStatus && this.currentStatus.current_track) {
        payload.video_id = this.currentStatus.current_track.video_id;
        payload.position = this.currentStatus.progress;
      }
      
      this.sendCommand('volume', payload);
      showVolumeToast(newVolume);
    });

    this.volumeDownBtn.addEventListener('click', () => {
      const currentVolume = parseInt(this.volumeSlider.value);
      const newVolume = Math.max(0, currentVolume - 1);
      this.volumeSlider.value = newVolume;
      this.volumeValue.textContent = newVolume + '%';
      
      // Activate volume control protection
      this.setVolumeControlActive();
      
      // Add track info for volume logging
      const payload = { volume: newVolume / 100 };
      if (this.currentStatus && this.currentStatus.current_track) {
        payload.video_id = this.currentStatus.current_track.video_id;
        payload.position = this.currentStatus.progress;
      }
      
      this.sendCommand('volume', payload);
      showVolumeToast(newVolume);
    });

    // Add touch and gesture support for volume
    let touchStartY = 0;
    let volumeStartValue = 0;

    this.volumeSlider.addEventListener('touchstart', (e) => {
      touchStartY = e.touches[0].clientY;
      volumeStartValue = parseInt(this.volumeSlider.value);
    }, { passive: true });

    this.volumeSlider.addEventListener('touchmove', (e) => {
      const touchCurrentY = e.touches[0].clientY;
      const deltaY = touchStartY - touchCurrentY;
      const volumeChange = Math.round(deltaY / 10); // Increased sensitivity for smoother control
      
      let newVolume = Math.max(0, Math.min(100, volumeStartValue + volumeChange));
      this.volumeSlider.value = newVolume;
      this.volumeValue.textContent = newVolume + '%';
    }, { passive: true });
  }
  
  setVolumeControlActive() {
    this.isVolumeControlActive = true;
    clearTimeout(this.volumeControlTimeout);
    this.volumeControlTimeout = setTimeout(() => {
      this.isVolumeControlActive = false;
      console.log('📱 Volume control protection deactivated');
    }, 3000); // 3 seconds cooldown
    console.log('📱 Volume control protection activated');
  }
  
  async sendCommand(command, data = {}) {
    try {
      const response = await fetch(`/api/remote/${command}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      
      if (response.ok) {
        console.log(`Command ${command} sent successfully`);
        // Immediately sync to get updated state
        this.syncStatus();
      } else {
        console.error(`Failed to send command ${command}`);
      }
    } catch (error) {
      console.error(`Error sending command ${command}:`, error);
      this.updateConnectionStatus(false);
    }
  }
  
  async syncStatus() {
    try {
      const response = await fetch('/api/remote/status');
      if (response.ok) {
        const status = await response.json();
        this.updateStatus(status);
        this.updateConnectionStatus(true);
      } else {
        this.updateConnectionStatus(false);
      }
    } catch (error) {
      console.error('Sync error:', error);
      this.updateConnectionStatus(false);
    }
  }
  
  updateStatus(status) {
    console.log('📱 Remote: Updating status:', status);
    this.currentStatus = status; // Store current status for volume logging
    
    // Update player type info
    if (status.player_type) {
      let playerTypeDisplay = '';
      switch (status.player_type) {
        case 'regular':
          playerTypeDisplay = '📁 Regular Playlist';
          break;
        case 'virtual':
          playerTypeDisplay = '❤️ Virtual Playlist';
          break;
        default:
          playerTypeDisplay = '🎵 Unknown Player';
      }
      
      if (status.player_source) {
        playerTypeDisplay += ` (${status.player_source})`;
      }
      
      this.playerTypeText.textContent = playerTypeDisplay;
      this.playerTypeInfo.style.display = 'block';
    } else {
      this.playerTypeInfo.style.display = 'none';
    }
    
    // Check if track changed (reset like state)
    const trackChanged = !this.currentTrack || 
      (status.current_track && status.current_track.video_id !== this.currentTrack.video_id);
    
    if (trackChanged && status.current_track) {
      this.currentTrack = status.current_track;
      // Reset like and dislike state when track changes
      this.likeBtn.classList.remove('like-active');
      this.dislikeBtn.classList.remove('dislike-active');
    }
    
    // Sync like/dislike button states from player
    if (status.like_active !== undefined) {
      if (status.like_active) {
        this.likeBtn.classList.add('like-active');
      } else {
        this.likeBtn.classList.remove('like-active');
      }
    }
    
    if (status.dislike_active !== undefined) {
      if (status.dislike_active) {
        this.dislikeBtn.classList.add('dislike-active');
      } else {
        this.dislikeBtn.classList.remove('dislike-active');
      }
    }
    
    // Update track info
    if (status.current_track) {
      const track = status.current_track;
      
      // Use YouTube title if available, otherwise clean up filename
      const displayName = track.youtube_title || (track.name ? track.name.replace(/\s*\[.*?\]$/, '') : 'Unknown Track');
      this.trackTitle.textContent = displayName;
      
      // Show channel info if available
      let statusText = status.playing ? 'Playing' : 'Paused';
      if (track.youtube_channel) {
        statusText += ` • ${track.youtube_channel}`;
      }
      this.trackStatus.textContent = statusText;
      
      // Update progress - use YouTube duration if available
      const duration = track.youtube_duration || track.duration;
      if (status.progress !== undefined && duration) {
        const percent = Math.min(100, Math.max(0, (status.progress / duration) * 100));
        this.progressBar.style.width = percent + '%';
        this.currentTime.textContent = this.formatTime(status.progress);
        
        // Use YouTube duration string if available, otherwise format seconds
        if (track.youtube_duration_string) {
          this.totalTime.textContent = track.youtube_duration_string;
        } else {
          this.totalTime.textContent = this.formatTime(duration);
        }
      } else {
        this.progressBar.style.width = '0%';
        this.currentTime.textContent = this.formatTime(status.progress || 0);
        this.totalTime.textContent = track.youtube_duration_string || (duration ? this.formatTime(duration) : '0:00');
      }
    } else {
      this.trackTitle.textContent = 'No track playing';
      this.trackStatus.textContent = 'Ready';
      this.progressBar.style.width = '0%';
      this.currentTime.textContent = '0:00';
      this.totalTime.textContent = '0:00';
    }
    
    // Update play button
    this.playBtn.innerHTML = status.playing 
      ? `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <rect x="6" y="4" width="4" height="16"></rect>
           <rect x="14" y="4" width="4" height="16"></rect>
         </svg>`
      : `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <polygon points="5,3 19,12 5,21"></polygon>
         </svg>`;
    this.playBtn.classList.toggle('playing', status.playing);
    
    // Update volume (only if not actively controlled by user)
    if (status.volume !== undefined && !this.isVolumeControlActive) {
      const volumePercent = Math.round(status.volume * 100);
      this.volumeSlider.value = volumePercent;
      this.volumeValue.textContent = volumePercent + '%';
    } else if (this.isVolumeControlActive) {
      console.log('📱 Volume sync blocked - user is actively controlling volume');
    }
    
    // Update last sync time
    this.lastSync.textContent = new Date().toLocaleTimeString();
  }
  
  updateConnectionStatus(connected) {
    this.connected = connected;
    this.statusDot.className = connected ? 'status-dot connected' : 'status-dot disconnected';
    this.statusText.textContent = connected ? 'Connected' : 'Disconnected';
    
    // Update last sync time
    this.lastSync.textContent = new Date().toLocaleTimeString();
  }
  
  // ==============================
  // LIKE SYNCHRONIZATION
  // ==============================
  
  // Function to sync likes after like/dislike actions (session-based only)
  async syncLikesAfterAction(video_id, action) {
    console.log(`📱 [Remote Like Sync] Syncing likes after ${action} for ${video_id}`);
    
    // Just sync status to update remote control with longer delay
    setTimeout(async () => {
      await this.syncStatus();
    }, 800);
  }
  
  formatTime(seconds) {
    if (!isFinite(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
  }
  
  startSync() {
    console.log('📱 Remote: Starting sync...');
    
    // Initial sync
    this.syncStatus();
    
    // Set up periodic sync
    this.syncInterval = setInterval(() => {
      this.syncStatus();
    }, 2000);
    
    // Set up server info update
    this.updateServerInfo();
    setInterval(() => {
      this.updateServerInfo();
    }, 30000);
  }
  
  updateServerInfo() {
    // This method needs to be implemented based on server info elements
    // For now, leaving it as placeholder
  }
}

// Initialize remote control when page loads
document.addEventListener('DOMContentLoaded', () => {
  const remoteControl = new RemoteControl();
  // Store reference for gesture control
  document.querySelector('.remote-container').remoteControlInstance = remoteControl;
  
  // Initialize keep awake early for immediate screen protection
  initKeepAwakeHandlers();
  
  // Hardware volume buttons integration
  initHardwareVolumeControl();
});

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
    
    // Android gesture-based volume control
    initAndroidGestureControl();
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

function initAndroidGestureControl() {
  console.log('📱 Initializing Android gesture control...');
  
  // Add swipe gestures on the entire remote container
  const container = document.querySelector('.remote-container');
  let startY = 0;
  let startX = 0;
  let startVolume = 0;
  
  container.addEventListener('touchstart', (e) => {
    if (e.touches.length === 1) {
      startY = e.touches[0].clientY;
      startX = e.touches[0].clientX;
      startVolume = parseInt(document.getElementById('volumeSlider').value);
    }
  }, { passive: true });
  
  container.addEventListener('touchmove', (e) => {
    if (e.touches.length === 1) {
      const currentY = e.touches[0].clientY;
      const currentX = e.touches[0].clientX;
      const deltaY = startY - currentY;
      const deltaX = Math.abs(startX - currentX);
      
      // Only process vertical swipes (ignore horizontal)
      if (Math.abs(deltaY) > 20 && deltaX < 50) {
        e.preventDefault();
        
        const volumeChange = Math.round(deltaY / 20); // Increased sensitivity for smoother control
        let newVolume = Math.max(0, Math.min(100, startVolume + volumeChange));
        
        const volumeSlider = document.getElementById('volumeSlider');
        const volumeValue = document.getElementById('volumeValue');
        
        volumeSlider.value = newVolume;
        volumeValue.textContent = newVolume + '%';
        
        showVolumeToast(newVolume);
      }
    }
  }, { passive: false });
  
  container.addEventListener('touchend', (e) => {
    // Send final volume to server
    const finalVolume = parseInt(document.getElementById('volumeSlider').value);
    const remoteControl = document.querySelector('.remote-container').remoteControlInstance;
    
    // Activate volume control protection
    if (remoteControl) {
      remoteControl.setVolumeControlActive();
    }
    
    // Prepare payload with track info
    const payload = { volume: finalVolume / 100 };
    if (remoteControl && remoteControl.currentStatus && remoteControl.currentStatus.current_track) {
      payload.video_id = remoteControl.currentStatus.current_track.video_id;
      payload.position = remoteControl.currentStatus.progress;
    }
    
    fetch('/api/remote/volume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    console.log('📱 Android gesture volume set to:', finalVolume + '%');
  }, { passive: true });
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
  instructionDiv.innerHTML = 'Swipe up/down anywhere or use volume buttons';
  
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
  showVolumeToast(newVolume);
  
  console.log('📱 Volume adjusted to:', newVolume + '%');
}

function showVolumeToast(volume) {
  // Remove existing toast
  const existingToast = document.getElementById('volumeToast');
  if (existingToast) {
    existingToast.remove();
  }
  
  // Create volume toast
  const toast = document.createElement('div');
  toast.id = 'volumeToast';
  toast.style.cssText = `
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: rgba(0, 0, 0, 0.8);
    color: white;
    padding: 20px 30px;
    border-radius: 15px;
    font-size: 18px;
    font-weight: bold;
    z-index: 10000;
    pointer-events: none;
    backdrop-filter: blur(10px);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
  `;
  
  const volumeIcon = volume === 0 
    ? `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
         <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
         <line x1="23" y1="9" x2="17" y2="15"></line>
         <line x1="17" y1="9" x2="23" y2="15"></line>
       </svg>`
    : volume < 30 
      ? `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
         </svg>`
      : volume < 70 
        ? `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
             <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
             <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
           </svg>`
        : `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
             <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
             <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
           </svg>`;
  toast.innerHTML = `${volumeIcon} ${volume}%`;
  
  document.body.appendChild(toast);
  
  // Auto remove after 1.5 seconds
  setTimeout(() => {
    if (toast.parentNode) {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }
  }, 1500);
}

async function requestWakeLock() {
  // Try Wake Lock API first (modern browsers, HTTPS required)
  if ('wakeLock' in navigator && location.protocol === 'https:') {
    try {
      if (wakeLock) {
        wakeLock.release();
      }
      
      wakeLock = await navigator.wakeLock.request('screen');
      keepAwakeMethod = 'wakeLock';
      keepAwakeActive = true;
      console.log('📱 Wake Lock API: Screen awake mode activated');
      updateKeepAwakeStatus();
      
      wakeLock.addEventListener('release', () => {
        console.log('📱 Wake Lock API: Screen awake mode deactivated');
        wakeLock = null;
        keepAwakeActive = false;
        updateKeepAwakeStatus();
        
        // Auto re-request wake lock after a short delay
        setTimeout(() => {
          if (document.visibilityState === 'visible') {
            console.log('📱 Auto re-requesting wake lock...');
            requestWakeLock();
          }
        }, 1000);
      });
      
      return true;
    } catch (error) {
      console.log('📱 Wake Lock API failed, trying fallback methods...');
    }
  }
  
  // Always start CSS animation method (very lightweight)
  initCSSKeepAwake();
  
  // Always start WebRTC method (additional layer)
  initWebRTCKeepAwake();
  
  // Fallback 1: Visible video method (works on most mobile browsers)
  if (tryVideoKeepAwake()) {
    keepAwakeMethod = 'video';
    keepAwakeActive = true;
    console.log('📱 Video method: Screen awake mode activated');
    updateKeepAwakeStatus();
    return true;
  }
  
  // Fallback 2: Periodic interaction simulation
  if (tryPeriodicKeepAwake()) {
    keepAwakeMethod = 'periodic';
    keepAwakeActive = true;
    console.log('📱 Periodic method: Screen awake mode activated');
    updateKeepAwakeStatus();
    return true;
  }
  
  // Last resort: Offer fullscreen mode (user interaction required)
  keepAwakeMethod = 'fullscreen';
  keepAwakeActive = false;
  console.log('📱 Only fullscreen mode available');
  updateKeepAwakeStatus();
  return false;
}

function initCSSKeepAwake() {
  // Create a continuously animating invisible element
  const animationElement = document.createElement('div');
  animationElement.id = 'cssKeepAwake';
  animationElement.style.cssText = `
    position: fixed;
    top: -3px;
    left: -3px;
    width: 1px;
    height: 1px;
    opacity: 0.001;
    pointer-events: none;
    z-index: -1000;
    animation: keepAwakeAnimation 2s infinite linear;
  `;
  
  // Create CSS animation keyframes
  const style = document.createElement('style');
  style.textContent = `
    @keyframes keepAwakeAnimation {
      0% { transform: translateX(0px) rotate(0deg); }
      25% { transform: translateX(0.1px) rotate(90deg); }
      50% { transform: translateX(0px) rotate(180deg); }
      75% { transform: translateX(-0.1px) rotate(270deg); }
      100% { transform: translateX(0px) rotate(360deg); }
    }
  `;
  
  document.head.appendChild(style);
  document.body.appendChild(animationElement);
  
  console.log('📱 CSS animation keep awake initialized');
}

function initWebRTCKeepAwake() {
  try {
    // Close existing WebRTC connection if any
    if (webRTCConnection) {
      webRTCConnection.close();
    }
    
    // Create a fake WebRTC connection to keep browser active
    const configuration = {
      iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
    };
    
    webRTCConnection = new RTCPeerConnection(configuration);
    
    // Create a fake video track from canvas
    const canvas = document.createElement('canvas');
    canvas.width = 1;
    canvas.height = 1;
    const ctx = canvas.getContext('2d');
    
    // Create minimal animation on canvas
    let frame = 0;
    const animateWebRTCCanvas = () => {
      ctx.fillStyle = frame % 2 === 0 ? '#000000' : '#000001';
      ctx.fillRect(0, 0, 1, 1);
      frame++;
      setTimeout(animateWebRTCCanvas, 5000); // Very slow animation
    };
    animateWebRTCCanvas();
    
    // Get stream from canvas
    const stream = canvas.captureStream(0.2); // Very low frame rate
    
    // Add tracks to WebRTC connection
    stream.getTracks().forEach(track => {
      webRTCConnection.addTrack(track, stream);
    });
    
    // Create data channel for additional activity
    const dataChannel = webRTCConnection.createDataChannel('keepAwake', {
      ordered: false,
      maxRetransmits: 0
    });
    
    // Send periodic data
    const sendKeepAliveData = () => {
      if (dataChannel.readyState === 'open') {
        dataChannel.send('ping');
      }
      setTimeout(sendKeepAliveData, 30000); // Every 30 seconds
    };
    
    dataChannel.addEventListener('open', () => {
      console.log('📱 WebRTC keep awake data channel opened');
      sendKeepAliveData();
    });
    
    // Create offer but don't actually connect anywhere
    webRTCConnection.createOffer().then(offer => {
      return webRTCConnection.setLocalDescription(offer);
    }).catch(() => {
      // Ignore errors, this is just for keep awake
    });
    
    console.log('📱 WebRTC keep awake initialized');
    return true;
    
  } catch (error) {
    console.log('📱 WebRTC keep awake failed:', error);
    return false;
  }
}

function tryVideoKeepAwake() {
  try {
    // Remove existing video if any
    if (hiddenVideo) {
      hiddenVideo.remove();
      hiddenVideo = null;
    }
    
    // Create barely visible video element (more effective than completely hidden)
    hiddenVideo = document.createElement('video');
    hiddenVideo.setAttribute('playsinline', 'true');
    hiddenVideo.setAttribute('webkit-playsinline', 'true');
    hiddenVideo.setAttribute('muted', 'true');
    hiddenVideo.setAttribute('autoplay', 'true');
    hiddenVideo.setAttribute('loop', 'true');
    hiddenVideo.setAttribute('controls', 'false');
    hiddenVideo.setAttribute('disablepictureinpicture', 'true');
    
    // Position video in bottom-right corner, barely visible but still "active"
    hiddenVideo.style.cssText = `
      position: fixed;
      bottom: 3px;
      right: 3px;
      width: 4px;
      height: 4px;
      opacity: 0.02;
      pointer-events: none;
      z-index: 998;
      border-radius: 1px;
      background: transparent;
    `;
    
    // Create animated canvas stream (more reliable than data URLs)
    const canvas = document.createElement('canvas');
    canvas.width = 8;
    canvas.height = 8;
    const ctx = canvas.getContext('2d');
    
    // Create subtle animation
    let frame = 0;
    const animateCanvas = () => {
      // Very subtle color changes - almost invisible
      const intensity = Math.sin(frame * 0.1) * 0.1 + 0.1;
      ctx.fillStyle = `rgba(0, 0, 0, ${intensity})`;
      ctx.fillRect(0, 0, 8, 8);
      frame++;
      requestAnimationFrame(animateCanvas);
    };
    animateCanvas();
    
    // Convert canvas to video stream
    const stream = canvas.captureStream(2); // 2 FPS for smoother animation
    hiddenVideo.srcObject = stream;
    
    document.body.appendChild(hiddenVideo);
    
    // Aggressive video management
    hiddenVideo.volume = 0;
    hiddenVideo.muted = true;
    
    // Function to force video playback
    const forceVideoPlay = async () => {
      try {
        await hiddenVideo.play();
        console.log('📱 Barely visible video playing successfully');
        
        // Very aggressive checks to keep video alive
        const videoKeepAliveInterval = setInterval(() => {
          if (!hiddenVideo) {
            clearInterval(videoKeepAliveInterval);
            return;
          }
          
          // Check if video is paused or ended
          if (hiddenVideo.paused || hiddenVideo.ended) {
            hiddenVideo.currentTime = 0;
            hiddenVideo.play().catch(() => {});
          }
          
          // Simulate interaction to keep video active
          hiddenVideo.dispatchEvent(new Event('timeupdate'));
          hiddenVideo.dispatchEvent(new Event('progress'));
          
        }, 300); // Check every 300ms - very frequent
        
        // Additional interaction simulation
        setInterval(() => {
          if (hiddenVideo) {
            hiddenVideo.dispatchEvent(new Event('canplay'));
            hiddenVideo.dispatchEvent(new Event('playing'));
          }
        }, 2000);
        
        return true;
        
      } catch (error) {
        console.log('📱 Canvas stream failed, trying data URL fallback...', error);
        
        // Fallback to data URL with same visible positioning
        hiddenVideo.srcObject = null;
        hiddenVideo.innerHTML = `
          <source src="data:video/webm;base64,GkXfo0AgQoaBAUL3gQFC8oEEQvOBCEKCQAR3ZWJtQoeBAkKFgQIYU4BnQI0VSalmQCgq17FAAw9CQE2AQAZ3aGFtbXlXQUAGd2hhbW15RIlACECPQAAAAAAAFlSua0AxrkAu14EBY8WBAZyBACK1nEADdW5khkAFVl9WUDglhohAA1ZQOIOBAeBABrCBCLqBCB9DtnVAIueBAKNAHIEAAIcBASPAgQjgAQAAAAAAABZUrmtAMa5ALteBAWPFgQGcgQAitZxAA3VuZIZABVZfVlA4JYaIQANWUDiDgQHgQAawgQi6gQgfQ7Z1QCLngQCjQByBAAMAAEALdq1+MQAK77+9z4Xs3QEtBIAGSIPLfENM3Heh9kfGvgAA" type="video/webm">
          <source src="data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAAAhFtZGF0AAAC6gYF//+c3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE1MiByMjg1NCBlOWE1OTAzIC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAxNyAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MzoweDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTMgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9MCBkaXJlY3Q9MSB3ZWlnaHRiPTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTI1IHNjZW5lY3V0PTQwIGludHJhX3JlZnJlc2g9MCByY19sb29rYWhlYWQ9NDAgcmM9Y3JmIG1idHJlZT0xIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRpbz0xLjQwIGFxPTE6MS4wMACAAAABWWWIhAA3//727P4FNjuY0JcRzeidDKmKQClAQEAAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAwAAAAAaAAADIGdtb29mAAAM4HRyYWsAAABcdGtoZAAAAAPsAAAAAAAAAAAAAAAAAAAAAAACAAAAYAAAAAEAAQAAAAAAAAAAAAAAAAAAAAAAAP//AAAAQAAAAAAAAAAAAAAAAAAAAEsW" type="video/mp4">
        `;
        hiddenVideo.load();
        return await hiddenVideo.play();
      }
    };
    
    // Try to start video immediately or wait for user interaction
    forceVideoPlay().catch(() => {
      console.log('📱 Video needs user interaction to start');
      
      // Create a more visible tooltip prompting user interaction
      const interactionPrompt = document.createElement('div');
      interactionPrompt.style.cssText = `
        position: fixed;
        bottom: 10px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 8px 15px;
        border-radius: 15px;
        font-size: 12px;
        z-index: 1000;
        pointer-events: none;
        backdrop-filter: blur(5px);
        border: 1px solid rgba(255, 255, 255, 0.1);
      `;
      interactionPrompt.textContent = 'Tap anywhere to activate screen protection';
      document.body.appendChild(interactionPrompt);
      
      // Auto-hide prompt after 5 seconds
      setTimeout(() => {
        if (interactionPrompt.parentNode) {
          interactionPrompt.remove();
        }
      }, 5000);
      
      // Wait for any user interaction to start video
      const startVideoOnInteraction = () => {
        forceVideoPlay().then(() => {
          if (interactionPrompt.parentNode) {
            interactionPrompt.remove();
          }
          document.removeEventListener('touchstart', startVideoOnInteraction);
          document.removeEventListener('click', startVideoOnInteraction);
          document.removeEventListener('keydown', startVideoOnInteraction);
        });
      };
      
      document.addEventListener('touchstart', startVideoOnInteraction, { once: true, passive: true });
      document.addEventListener('click', startVideoOnInteraction, { once: true });
      document.addEventListener('keydown', startVideoOnInteraction, { once: true });
    });
    
    return true;
  } catch (error) {
    console.log('📱 Video keep awake method failed completely:', error);
    if (hiddenVideo) {
      hiddenVideo.remove();
      hiddenVideo = null;
    }
    return false;
  }
}

function tryPeriodicKeepAwake() {
  try {
    // Clear existing interval
    if (keepAwakeInterval) {
      clearInterval(keepAwakeInterval);
    }
    
    console.log('📱 Starting aggressive periodic keep awake method');
    
    // Multiple types of periodic events to prevent sleep
    keepAwakeInterval = setInterval(() => {
      try {
        // Method 1: Tiny canvas animation
        const canvas = document.createElement('canvas');
        canvas.width = 1;
        canvas.height = 1;
        canvas.style.cssText = `
          position: fixed;
          top: -2px;
          left: -2px;
          opacity: 0.01;
          pointer-events: none;
          z-index: -1000;
        `;
        document.body.appendChild(canvas);
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, 1, 1);
        setTimeout(() => canvas.remove(), 100);
        
        // Method 2: Focus shift
        const hiddenInput = document.createElement('input');
        hiddenInput.style.cssText = `
          position: fixed;
          top: -10px;
          left: -10px;
          width: 1px;
          height: 1px;
          opacity: 0;
          pointer-events: none;
          z-index: -1000;
        `;
        document.body.appendChild(hiddenInput);
        hiddenInput.focus();
        hiddenInput.blur();
        setTimeout(() => hiddenInput.remove(), 100);
        
        // Method 3: Vibration API (if available)
        if ('vibrate' in navigator) {
          navigator.vibrate(1);
        }
        
        // Method 4: Document interaction
        document.dispatchEvent(new Event('touchstart', { bubbles: true }));
        document.dispatchEvent(new Event('mousemove', { bubbles: true }));
        
        // Method 5: Window animation frame
        requestAnimationFrame(() => {
          const dummy = document.createElement('div');
          dummy.style.transform = 'translateX(0.1px)';
          document.body.appendChild(dummy);
          setTimeout(() => dummy.remove(), 10);
        });
        
        console.log('📱 Keep awake ping sent');
        
      } catch (error) {
        console.log('📱 Keep awake ping error:', error);
      }
      
    }, 4000); // Every 4 seconds - very frequent
    
    // Additional audio context method
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      
      gainNode.gain.value = 0; // Silent
      oscillator.frequency.value = 20000; // Very high frequency
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.001); // Very short
      
      // Keep audio context alive
      setInterval(() => {
        if (audioContext.state === 'suspended') {
          audioContext.resume().catch(() => {});
        }
      }, 10000);
      
      console.log('📱 Audio context keep awake initialized');
    } catch (error) {
      console.log('📱 Audio context method failed:', error);
    }
    
    return true;
  } catch (error) {
    console.log('📱 Periodic keep awake method failed:', error);
    return false;
  }
}

function updateKeepAwakeStatus() {
  // Update or create keep awake indicator
  let indicator = document.getElementById('keepAwakeIndicator');
  
  if (!indicator) {
    indicator = document.createElement('div');
    indicator.id = 'keepAwakeIndicator';
    indicator.style.cssText = `
      position: fixed;
      top: 10px;
      right: 10px;
      background: rgba(0, 0, 0, 0.7);
      color: white;
      padding: 6px 12px;
      border-radius: 15px;
      font-size: 11px;
      z-index: 1000;
      backdrop-filter: blur(5px);
      transition: all 0.3s ease;
      pointer-events: auto;
      cursor: pointer;
      user-select: none;
      border: 1px solid rgba(255, 255, 255, 0.1);
    `;
    document.body.appendChild(indicator);
    
    // Add click to toggle keep awake
    indicator.addEventListener('click', () => {
      if (keepAwakeActive) {
        stopKeepAwake();
        showKeepAwakeToast('Screen keep awake disabled');
      } else if (keepAwakeMethod === 'fullscreen') {
        // Request fullscreen mode
        requestFullscreenKeepAwake();
      } else {
        requestWakeLock();
        showKeepAwakeToast('Screen keep awake enabled');
      }
    });
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
      if (indicator.style.opacity !== '0.5') {
        indicator.style.opacity = '0.5';
        indicator.style.transform = 'scale(0.9)';
      }
    }, 5000);
  }
  
  if (keepAwakeActive) {
    switch (keepAwakeMethod) {
      case 'wakeLock':
        indicator.innerHTML = '🔒 Keep Awake (API)';
        indicator.style.background = 'rgba(34, 197, 94, 0.8)';
        indicator.style.borderColor = 'rgba(34, 197, 94, 0.3)';
        break;
      case 'video':
        indicator.innerHTML = '🎥 Keep Awake (Active)';
        indicator.style.background = 'rgba(59, 130, 246, 0.8)';
        indicator.style.borderColor = 'rgba(59, 130, 246, 0.3)';
        break;
      case 'periodic':
        indicator.innerHTML = '⏰ Keep Awake (Touch)';
        indicator.style.background = 'rgba(168, 85, 247, 0.8)';
        indicator.style.borderColor = 'rgba(168, 85, 247, 0.3)';
        break;
      case 'fullscreen':
        indicator.innerHTML = '📺 Keep Awake (Fullscreen)';
        indicator.style.background = 'rgba(245, 158, 11, 0.8)';
        indicator.style.borderColor = 'rgba(245, 158, 11, 0.3)';
        break;
    }
  } else {
    switch (keepAwakeMethod) {
      case 'fullscreen':
        indicator.innerHTML = '📺 Tap for Fullscreen';
        indicator.style.background = 'rgba(245, 158, 11, 0.8)';
        indicator.style.borderColor = 'rgba(245, 158, 11, 0.3)';
        break;
      case 'none':
        indicator.innerHTML = '❌ Keep Awake N/A';
        indicator.style.background = 'rgba(107, 114, 128, 0.8)';
        indicator.style.borderColor = 'rgba(107, 114, 128, 0.3)';
        break;
      default:
        indicator.innerHTML = '😴 Tap to Keep Awake';
        indicator.style.background = 'rgba(239, 68, 68, 0.8)';
        indicator.style.borderColor = 'rgba(239, 68, 68, 0.3)';
    }
  }
}

function requestFullscreenKeepAwake() {
  if (document.fullscreenElement) {
    // Exit fullscreen
    document.exitFullscreen().then(() => {
      keepAwakeActive = false;
      updateKeepAwakeStatus();
      showKeepAwakeToast('Exited fullscreen mode');
    }).catch(() => {
      showKeepAwakeToast('Failed to exit fullscreen');
    });
  } else {
    // Enter fullscreen
    const element = document.documentElement;
    const requestFullscreen = element.requestFullscreen || 
                             element.webkitRequestFullscreen || 
                             element.mozRequestFullScreen || 
                             element.msRequestFullscreen;
    
    if (requestFullscreen) {
      requestFullscreen.call(element).then(() => {
        keepAwakeActive = true;
        updateKeepAwakeStatus();
        showKeepAwakeToast('Fullscreen mode activated - screen will stay awake');
        
        // Listen for fullscreen changes
        const handleFullscreenChange = () => {
          if (!document.fullscreenElement) {
            keepAwakeActive = false;
            updateKeepAwakeStatus();
            showKeepAwakeToast('Fullscreen exited - screen may sleep');
            document.removeEventListener('fullscreenchange', handleFullscreenChange);
            document.removeEventListener('webkitfullscreenchange', handleFullscreenChange);
            document.removeEventListener('mozfullscreenchange', handleFullscreenChange);
            document.removeEventListener('msfullscreenchange', handleFullscreenChange);
          }
        };
        
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
        document.addEventListener('mozfullscreenchange', handleFullscreenChange);
        document.addEventListener('msfullscreenchange', handleFullscreenChange);
        
      }).catch(() => {
        showKeepAwakeToast('Fullscreen request failed');
      });
    } else {
      showKeepAwakeToast('Fullscreen not supported');
      keepAwakeMethod = 'none';
      updateKeepAwakeStatus();
    }
  }
}

function showKeepAwakeToast(message) {
  // Remove existing toast
  const existingToast = document.getElementById('keepAwakeToast');
  if (existingToast) {
    existingToast.remove();
  }
  
  // Create keep awake toast
  const toast = document.createElement('div');
  toast.id = 'keepAwakeToast';
  toast.style.cssText = `
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: rgba(0, 0, 0, 0.9);
    color: white;
    padding: 15px 25px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 500;
    z-index: 10000;
    pointer-events: none;
    backdrop-filter: blur(10px);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.1);
    max-width: 80vw;
    text-align: center;
  `;
  
  toast.textContent = message;
  document.body.appendChild(toast);
  
  // Auto remove after 3 seconds for longer messages
  setTimeout(() => {
    if (toast.parentNode) {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }
  }, 3000);
}

function initKeepAwakeHandlers() {
  // Request keep awake when page becomes visible
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && !keepAwakeActive) {
      console.log('📱 Page became visible, requesting keep awake...');
      setTimeout(requestWakeLock, 500);
    }
  });
  
  // Re-request keep awake on focus
  window.addEventListener('focus', () => {
    if (!keepAwakeActive) {
      console.log('📱 Window focused, requesting keep awake...');
      setTimeout(requestWakeLock, 500);
    }
  });
  
  // Stop keep awake when page is hidden (save battery)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      console.log('📱 Page hidden, stopping keep awake...');
      stopKeepAwake();
    }
  });
  
  // Initial keep awake request
  console.log('📱 Initializing keep awake system...');
  requestWakeLock();
}

function stopKeepAwake() {
  // Stop wake lock
  if (wakeLock) {
    wakeLock.release();
    wakeLock = null;
  }
  
  // Stop video
  if (hiddenVideo) {
    hiddenVideo.pause();
    hiddenVideo.remove();
    hiddenVideo = null;
  }
  
  // Stop periodic method
  if (keepAwakeInterval) {
    clearInterval(keepAwakeInterval);
    keepAwakeInterval = null;
  }
  
  // Stop CSS animation
  const cssKeepAwakeElement = document.getElementById('cssKeepAwake');
  if (cssKeepAwakeElement) {
    cssKeepAwakeElement.remove();
  }
  
  // Stop WebRTC connection
  if (webRTCConnection) {
    webRTCConnection.close();
    webRTCConnection = null;
  }
  
  // Exit fullscreen if active
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {});
  }
  
  keepAwakeActive = false;
  console.log('📱 Keep awake stopped');
  updateKeepAwakeStatus();
} 