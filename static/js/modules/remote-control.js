/**
 * Remote Control Module
 * Core class for managing remote control functionality and player synchronization
 */

// Import dependencies (use global reference)
function getShowVolumeToast() {
  return window.showVolumeToast || (window.ToastNotifications && window.ToastNotifications.showVolumeToast) || null;
}

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
      const toast = getShowVolumeToast();
      if (toast) toast(newVolume);
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
      const toast = getShowVolumeToast();
      if (toast) toast(newVolume);
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

// Export class for browser environment
window.RemoteControl = RemoteControl; 