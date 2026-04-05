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
    this.deleteBtn = document.getElementById('deleteBtn');
    this.likeBtn = document.getElementById('likeBtn');
    this.dislikeBtn = document.getElementById('dislikeBtn');
    this.youtubeBtn = document.getElementById('youtubeBtn');
    
    // Volume controls
    this.volumeSlider = document.getElementById('volumeSlider');
    this.volumeValue = document.getElementById('volumeValue');
    this.volumeUpBtn = document.getElementById('volumeUpBtn');
    this.volumeDownBtn = document.getElementById('volumeDownBtn');
    
    // Info elements
    this.serverInfo = document.getElementById('serverInfo');
    this.lastSync = document.getElementById('lastSync');

    this.playlistSourceSelect = document.getElementById('playlistSourceSelect');
    this.playlistSourcesRefreshBtn = document.getElementById('playlistSourcesRefreshBtn');
    this._playlistSources = null;
    this._suppressPlaylistSourceChange = false;
  }
  
  attachEvents() {
    // Control buttons
    this.prevBtn.addEventListener('click', () => this.sendCommand('prev'));
    this.playBtn.addEventListener('click', () => this.sendCommand('play'));
    this.nextBtn.addEventListener('click', () => this.sendCommand('next'));
    this.deleteBtn.addEventListener('click', async () => {
      // Get current track info for confirmation
      const hasTrack = this.currentStatus && this.currentStatus.current_track;
      const trackName = hasTrack ? (this.currentStatus.current_track.name || 'Unknown track') : null;
      const videoId = hasTrack ? (this.currentStatus.current_track.video_id || 'Unknown ID') : null;
      const plainMessage = hasTrack
        ? `Delete current track "${(trackName || '').replace(/\s*\[.*?\]$/, '')}" (${videoId}) from playlist?\n\nTrack will be moved to trash and can be restored.`
        : 'Delete current track from playlist?\n\nTrack will be moved to trash and can be restored.';

      let confirmed = false;
      if (window.showConfirmDialog) {
        const htmlMessage = hasTrack
          ? `Delete current track "${(trackName || '').replace(/\s*\[.*?\]$/, '')}" (${videoId}) from playlist?<br/><br/>Track will be moved to trash and can be restored.`
          : 'Delete current track from playlist?<br/><br/>Track will be moved to trash and can be restored.';
        confirmed = await window.showConfirmDialog({
          title: 'Delete Track',
          htmlMessage,
          confirmText: 'Delete',
          cancelText: 'Cancel',
          destructive: true
        });
      } else {
        // Safe fallback
        confirmed = window.confirm(plainMessage);
      }

      if (confirmed) {
        await this.sendCommand('delete');
      }
    });
    this.likeBtn.addEventListener('click', async () => {
      await this.sendCommand('like');
    });
    this.dislikeBtn.addEventListener('click', async () => {
      await this.sendCommand('dislike');
    });
    this.youtubeBtn.addEventListener('click', () => this.sendCommand('youtube'));
    
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

    if (this.playlistSourceSelect) {
      this.playlistSourceSelect.addEventListener('change', async () => {
        if (this._suppressPlaylistSourceChange) return;
        const path = this.playlistSourceSelect.value;
        if (!path) return;
        await this.sendCommand('switch_source', { path });
      });
    }
    if (this.playlistSourcesRefreshBtn) {
      this.playlistSourcesRefreshBtn.addEventListener('click', () => this.loadPlaylistSources());
    }
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
    
    const prevVideoId = this.currentTrack?.video_id ?? null;
    const nextVideoId = status.current_track?.video_id ?? null;
    const trackIdentityChanged = prevVideoId !== nextVideoId;

    if (trackIdentityChanged) {
      this.currentTrack = status.current_track || null;
      this.likeBtn.classList.remove('like-active');
      this.dislikeBtn.classList.remove('dislike-active');
    }

    // PLAYER_STATE.like_active may still be from the *previous* track for one poll after advance;
    // re-applying it here would undo the reset above. Skip one cycle when video_id actually changed.
    const skipReactionFromServer =
      prevVideoId !== null && nextVideoId !== null && prevVideoId !== nextVideoId;

    if (!skipReactionFromServer) {
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

    this.syncPlaylistSelectToStatus();
  }

  decodePath(p) {
    try {
      return decodeURIComponent(p);
    } catch {
      return p;
    }
  }

  renderPlaylistSourceSelect() {
    const sel = this.playlistSourceSelect;
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = '— Select playlist —';
    sel.appendChild(placeholder);

    const data = this._playlistSources;
    if (!data || data.status !== 'ok') {
      const err = document.createElement('option');
      err.value = '';
      err.textContent = 'Could not load playlist list';
      err.disabled = true;
      sel.appendChild(err);
      return;
    }

    const appendGroup = (label, items) => {
      if (!items || !items.length) return;
      const og = document.createElement('optgroup');
      og.label = label;
      for (const it of items) {
        const o = document.createElement('option');
        o.value = it.path;
        o.textContent = it.label || it.name || it.path;
        og.appendChild(o);
      }
      sel.appendChild(og);
    };

    appendGroup('Folders', data.regular);
    appendGroup('By net likes', data.virtual);

    this._runPlaylistSelectProgrammatic(() => {
      if (prev && [...sel.options].some((o) => o.value === prev)) {
        sel.value = prev;
      }
    });
  }

  /** Avoid firing change → switch_source when syncing from player status. */
  _runPlaylistSelectProgrammatic(fn) {
    this._suppressPlaylistSourceChange = true;
    try {
      fn();
    } finally {
      queueMicrotask(() => {
        this._suppressPlaylistSourceChange = false;
      });
    }
  }

  syncPlaylistSelectToStatus() {
    const sel = this.playlistSourceSelect;
    if (!sel || !this.currentStatus || !this.currentStatus.player_source) return;
    const want = this.decodePath(this.currentStatus.player_source);
    this._runPlaylistSelectProgrammatic(() => {
      for (const opt of sel.options) {
        if (!opt.value) continue;
        if (this.decodePath(opt.value) === want) {
          sel.value = opt.value;
          return;
        }
      }
    });
  }

  async loadPlaylistSources() {
    if (!this.playlistSourceSelect) return;
    try {
      const response = await fetch('/api/remote/playlist_sources');
      const data = await response.json();
      this._playlistSources = data;
      this.renderPlaylistSourceSelect();
      this.syncPlaylistSelectToStatus();
    } catch (e) {
      console.warn('Playlist sources load failed:', e);
      this._playlistSources = { status: 'error' };
      this.renderPlaylistSourceSelect();
    }
  }
  
  updateConnectionStatus(connected) {
    this.connected = connected;
    this.statusDot.className = connected ? 'status-dot connected' : 'status-dot disconnected';
    this.statusText.textContent = connected ? 'Connected' : 'Disconnected';
    
    // Update last sync time
    this.lastSync.textContent = new Date().toLocaleTimeString();
  }
  
  formatTime(seconds) {
    if (!isFinite(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
  }
  
  startSync() {
    console.log('📱 Remote: Starting sync...');

    this.loadPlaylistSources();
    
    // Initial sync
    this.syncStatus();
    
    // Set up periodic sync
    this.syncInterval = setInterval(() => {
      this.syncStatus();
    }, 1000);
    
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