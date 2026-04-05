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

    /** Same track as main player on this device (another room). */
    this.followAudioActive = false;
    this.followAudioEl = null;
    this.followVideoEl = null;
    /** @type {'audio'|'video'|null} */
    this._followMediaKind = null;
    this._followTrackKey = null;
    this._followLoadPending = false;

    /** NTP-style offset: estimated_server_ms ≈ Date.now() + median offset. */
    this._clockSkewSamples = [];
    this._syncMs = 1000;
    /** Avoid repeated currentTime seeks (causes stutter on mobile). */
    this._followLastHardSeekMs = 0;
    this._volumeTouchTimer = null;
    
    this.initElements();
    this.attachEvents();
    this.startSync();
  }
  
  initElements() {
    // Status elements
    this.statusDot = document.getElementById('statusDot');
    this.statusText = document.getElementById('statusText');
    this.reloadPageBtn = document.getElementById('remoteReloadBtn');
    
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

    this.followAudioBtn = document.getElementById('followAudioBtn');
    this.followAudioLabel = document.getElementById('followAudioLabel');
    this.followAudioEl = document.getElementById('remoteFollowAudio');
    this.followVideoEl = document.getElementById('remoteFollowVideo');
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
      const volume = parseInt(e.target.value, 10);
      this.volumeValue.textContent = volume + '%';
      this.setVolumeControlActive();
      this._sendVolumePayload(volume);
    });

    // Volume buttons
    this.volumeUpBtn.addEventListener('click', () => {
      const currentVolume = parseInt(this.volumeSlider.value, 10) || 0;
      const newVolume = Math.min(100, currentVolume + 1);
      this.volumeSlider.value = newVolume;
      this.volumeValue.textContent = newVolume + '%';
      this.setVolumeControlActive();
      this._sendVolumePayload(newVolume);
      const toast = getShowVolumeToast();
      if (toast) toast(newVolume);
    });

    this.volumeDownBtn.addEventListener('click', () => {
      const currentVolume = parseInt(this.volumeSlider.value, 10) || 0;
      const newVolume = Math.max(0, currentVolume - 1);
      this.volumeSlider.value = newVolume;
      this.volumeValue.textContent = newVolume + '%';
      this.setVolumeControlActive();
      this._sendVolumePayload(newVolume);
      const toast = getShowVolumeToast();
      if (toast) toast(newVolume);
    });

    // Touch volume: keep "user adjusting" guard on (sync was overwriting slider) + send to server.
    let touchStartY = 0;
    let volumeStartValue = 0;

    this.volumeSlider.addEventListener('touchstart', (e) => {
      touchStartY = e.touches[0].clientY;
      volumeStartValue = parseInt(this.volumeSlider.value, 10) || 0;
      this.setVolumeControlActive();
    }, { passive: true });

    this.volumeSlider.addEventListener('touchmove', (e) => {
      const touchCurrentY = e.touches[0].clientY;
      const deltaY = touchStartY - touchCurrentY;
      const volumeChange = Math.round(deltaY / 10);

      const newVolume = Math.max(0, Math.min(100, volumeStartValue + volumeChange));
      this.volumeSlider.value = newVolume;
      this.volumeValue.textContent = newVolume + '%';
      this.setVolumeControlActive();
      this._throttledSendTouchVolume(newVolume);
    }, { passive: true });

    this.volumeSlider.addEventListener('touchend', () => {
      clearTimeout(this._volumeTouchTimer);
      this._volumeTouchTimer = null;
      const v = parseInt(this.volumeSlider.value, 10);
      if (Number.isFinite(v)) {
        this.setVolumeControlActive();
        this._sendVolumePayload(v);
      }
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

    if (this.reloadPageBtn) {
      this.reloadPageBtn.addEventListener('click', () => window.location.reload());
    }

    if (this.followAudioBtn) {
      this.followAudioBtn.addEventListener('click', () => this.toggleFollowAudio());
    }
    const onFollowMediaError = () => {
      if (!this.followAudioActive) return;
      this._followLoadPending = false;
      const toast = window.ToastNotifications && window.ToastNotifications.showToast;
      if (toast) {
        toast('Could not play on this device (format or codec). Try MP4/AAC or MP3.', {
          id: 'followAudioError',
          backgroundColor: 'rgba(139, 0, 0, 0.92)',
        });
      }
    };
    if (this.followAudioEl) this.followAudioEl.addEventListener('error', onFollowMediaError);
    if (this.followVideoEl) this.followVideoEl.addEventListener('error', onFollowMediaError);
  }

  _stopBothFollowMedia() {
    [this.followAudioEl, this.followVideoEl].forEach((el) => {
      if (!el) return;
      el.playbackRate = 1;
      el.pause();
      el.removeAttribute('src');
      try {
        el.load();
      } catch (e) {
        /* ignore */
      }
    });
  }

  /** @returns {HTMLMediaElement|null} */
  _followActiveMediaEl() {
    if (this._followMediaKind === 'audio') return this.followAudioEl;
    if (this._followMediaKind === 'video') return this.followVideoEl;
    return null;
  }

  /**
   * @param {string} absUrl
   * @returns {HTMLMediaElement|null}
   */
  _mediaElForUrl(absUrl) {
    const useAudio = this._isAudioOnlyUrl(absUrl);
    const nextKind = useAudio ? 'audio' : 'video';
    if (this._followMediaKind !== nextKind) {
      const old = this._followActiveMediaEl();
      if (old) {
        old.pause();
        old.removeAttribute('src');
        try {
          old.load();
        } catch (e) {
          /* ignore */
        }
      }
      this._followMediaKind = nextKind;
    }
    return useAudio ? this.followAudioEl : this.followVideoEl;
  }

  /**
   * @param {string} url
   * @returns {boolean}
   */
  _isAudioOnlyUrl(url) {
    const ext = (url.split('?')[0].split('.').pop() || '').toLowerCase();
    return ['mp3', 'm4a', 'aac', 'flac', 'opus', 'ogg', 'oga', 'wav'].includes(ext);
  }

  toggleFollowAudio() {
    this.followAudioActive = !this.followAudioActive;
    this.updateFollowAudioButton();
    if (!this.followAudioActive) {
      this._followTrackKey = null;
      this._followLoadPending = false;
      this._followMediaKind = null;
      this._stopBothFollowMedia();
      this._syncMs = 1000;
      this._restartSyncLoop();
      return;
    }
    if (this.currentStatus) {
      this.updateFollowAudioAfterStatus(this.currentStatus);
    }
    this._syncMs = 400;
    this._restartSyncLoop();
    this.syncStatus();
  }

  updateFollowAudioButton() {
    if (!this.followAudioBtn || !this.followAudioLabel) return;
    this.followAudioBtn.classList.toggle('active', this.followAudioActive);
    this.followAudioLabel.textContent = this.followAudioActive ? 'Stop local audio' : 'Listen here';
    this.followAudioBtn.title = this.followAudioActive
      ? 'Stop playback on this phone'
      : 'Play the same track on this phone (for another room). One tap unlocks audio in the browser.';
  }

  /**
   * @param {object} track
   * @returns {string|null}
   */
  _buildMediaUrl(track) {
    if (!track) return null;
    let path = track.url;
    if (!path && track.relpath) {
      const parts = String(track.relpath).replace(/\\/g, '/').split('/').filter(Boolean);
      path = '/media/' + parts.map(encodeURIComponent).join('/');
    }
    if (!path || typeof path !== 'string') return null;
    try {
      return new URL(path, window.location.origin).href;
    } catch {
      return null;
    }
  }

  _followTrackIdentity(track) {
    if (!track) return null;
    return track.video_id || track.relpath || track.url || null;
  }

  /**
   * If the main player is muted (volume 0), still hear on the phone.
   * @param {object} st
   * @param {HTMLMediaElement} mediaEl
   */
  _applyFollowVolumeFromStatus(st, mediaEl) {
    const v = Number(st.volume);
    if (!Number.isFinite(v) || v <= 0.02) {
      mediaEl.volume = 1.0;
    } else {
      mediaEl.volume = Math.min(1, Math.max(0, v));
    }
  }

  _recordClockSkewSample(theta) {
    if (!Number.isFinite(theta)) return;
    this._clockSkewSamples.push(theta);
    while (this._clockSkewSamples.length > 9) {
      this._clockSkewSamples.shift();
    }
  }

  /** @returns {number|null} server_ms − client_ms */
  _medianClockOffset() {
    const arr = this._clockSkewSamples;
    if (!arr.length) return null;
    const sorted = [...arr].sort((a, b) => a - b);
    return sorted[Math.floor(sorted.length / 2)];
  }

  /** @returns {number|null} */
  _estimatedServerNowMs() {
    const off = this._medianClockOffset();
    if (off == null) return null;
    return Date.now() + off;
  }

  /**
   * Playback position extrapolated with server anchor + clock skew (tighter than raw progress).
   * @param {object} status
   * @returns {number}
   */
  _expectedProgressSec(status) {
    const anchorMs = status.playback_anchor_server_ms;
    const pos = status.playback_anchor_position;
    const playing = status.playback_anchor_playing;
    const anchorKey = status.playback_anchor_track_key;
    const raw = Math.max(0, Number(status.progress) || 0);
    if (anchorMs == null || pos == null || anchorKey == null) {
      return raw;
    }
    const curKey = this._followTrackIdentity(status.current_track);
    if (curKey == null || curKey !== anchorKey) {
      return raw;
    }
    const serverNow = this._estimatedServerNowMs();
    if (serverNow == null) {
      return raw;
    }
    if (!playing) {
      return Math.max(0, Number(pos) || 0);
    }
    return Math.max(0, Number(pos) + (serverNow - anchorMs) / 1000);
  }

  /**
   * Gentle speed nudge instead of seek when drift is moderate (stream_client-style).
   * @param {HTMLMediaElement} mediaEl
   * @param {number} deltaSec target − currentTime (signed)
   */
  _followNudgePlaybackRate(mediaEl, deltaSec) {
    const ad = Math.abs(deltaSec);
    if (ad < 0.05) {
      if (mediaEl.playbackRate !== 1) mediaEl.playbackRate = 1;
      return;
    }
    const cap = 0.05;
    const adj = Math.max(-cap, Math.min(cap, deltaSec * 0.22));
    mediaEl.playbackRate = 1 + adj;
  }

  /**
   * Keep hidden media element in sync with PLAYER_STATE from /api/remote/status.
   * @param {object} status
   */
  updateFollowAudioAfterStatus(status) {
    if (!this.followAudioActive) return;

    const track = status.current_track;
    const absUrl = this._buildMediaUrl(track);
    if (!track || !absUrl) {
      this._followTrackKey = null;
      this._followLoadPending = false;
      this._followMediaKind = null;
      this._stopBothFollowMedia();
      return;
    }

    const mediaEl = this._mediaElForUrl(absUrl);
    if (!mediaEl) return;
    if (mediaEl.tagName === 'VIDEO') {
      mediaEl.setAttribute('playsinline', '');
      mediaEl.playsInline = true;
    }

    const key = this._followTrackIdentity(track);
    if (this._followTrackKey !== key) {
      this._followTrackKey = key;
      this._followLoadPending = true;
      this._followLastHardSeekMs = 0;
      mediaEl.playbackRate = 1;
      mediaEl.src = absUrl;

      // Every new src: start muted + play() immediately. Mobile browsers block
      // unmuted play() from loadedmetadata (no user gesture); muted autoplay
      // usually still works after the user enabled "Listen here" once.
      mediaEl.muted = true;
      const pr = mediaEl.play();
      if (pr && typeof pr.then === 'function') {
        pr.catch((e) => console.warn('Follow play after src change:', e));
      }

      const expectedKey = key;
      let metaApplied = false;
      const onMeta = () => {
        if (metaApplied) return;
        if (!this.followAudioActive || this._followTrackKey !== expectedKey) return;
        metaApplied = true;
        this._followLoadPending = false;
        const st = this.currentStatus || status;
        const pos = this._expectedProgressSec(st);
        try {
          mediaEl.currentTime = pos;
        } catch (e) {
          console.warn('Follow-media seek failed:', e);
        }
        this._applyFollowVolumeFromStatus(st, mediaEl);
        mediaEl.playbackRate = 1;
        mediaEl.muted = false;
        if (st.playing) {
          mediaEl.play().catch((err) => console.warn('Follow-media play failed:', err));
        } else {
          mediaEl.pause();
        }
      };

      mediaEl.addEventListener('loadedmetadata', onMeta, { once: true });
      if (mediaEl.readyState >= 1) {
        queueMicrotask(() => onMeta());
      }
      return;
    }

    if (this._followLoadPending) return;

    this._applyFollowVolumeFromStatus(status, mediaEl);

    const target = this._expectedProgressSec(status);
    const delta = target - mediaEl.currentTime;
    const drift = Math.abs(delta);

    const hardSeekDrift = 3.0;
    const emergencySeekDrift = 10.0;
    const hardSeekCooldownMs = 4500;
    const now = Date.now();

    if (status.playing) {
      const sinceSeek = now - this._followLastHardSeekMs;
      const doHardSeek =
        drift >= emergencySeekDrift ||
        (drift >= hardSeekDrift && sinceSeek >= hardSeekCooldownMs);

      if (doHardSeek) {
        try {
          mediaEl.playbackRate = 1;
          mediaEl.currentTime = Math.max(0, target);
          this._followLastHardSeekMs = now;
        } catch (e) {
          console.warn('Follow-media resync seek failed:', e);
        }
      } else {
        this._followNudgePlaybackRate(mediaEl, delta);
      }
      if (mediaEl.paused) {
        mediaEl.muted = false;
        mediaEl.play().catch((err) => console.warn('Follow-media play failed:', err));
      }
    } else {
      mediaEl.pause();
      mediaEl.playbackRate = 1;
      if (drift > 2.5) {
        try {
          mediaEl.currentTime = Math.max(0, target);
        } catch (e) {
          console.warn('Follow-media pause seek failed:', e);
        }
      }
    }
  }

  _sendVolumePayload(volumePercent) {
    const volume = Math.max(0, Math.min(100, volumePercent)) / 100;
    const payload = { volume };
    if (this.currentStatus && this.currentStatus.current_track) {
      payload.video_id = this.currentStatus.current_track.video_id;
      payload.position = this.currentStatus.progress;
    }
    this.sendCommand('volume', payload);
  }

  _throttledSendTouchVolume(newVolume) {
    clearTimeout(this._volumeTouchTimer);
    this._volumeTouchTimer = setTimeout(() => {
      this._volumeTouchTimer = null;
      this._sendVolumePayload(newVolume);
    }, 80);
  }
  
  setVolumeControlActive() {
    this.isVolumeControlActive = true;
    clearTimeout(this.volumeControlTimeout);
    this.volumeControlTimeout = setTimeout(() => {
      this.isVolumeControlActive = false;
      console.log('📱 Volume control protection deactivated');
    }, 4500);
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
      const t0 = Date.now();
      const response = await fetch(`/api/remote/status?client_ms=${t0}`);
      const t3 = Date.now();
      if (response.ok) {
        const status = await response.json();
        if (status.time_sync) {
          const { t1_server_ms, t2_server_ms, client_ms } = status.time_sync;
          const theta = ((t1_server_ms - client_ms) + (t2_server_ms - t3)) / 2;
          this._recordClockSkewSample(theta);
        }
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
      
      // Update progress - use YouTube duration if available (clock-synced when anchor + skew exist)
      const duration = track.youtube_duration || track.duration;
      const displayProgress = this._expectedProgressSec(status);
      if (displayProgress !== undefined && duration) {
        const percent = Math.min(100, Math.max(0, (displayProgress / duration) * 100));
        this.progressBar.style.width = percent + '%';
        this.currentTime.textContent = this.formatTime(displayProgress);
        
        // Use YouTube duration string if available, otherwise format seconds
        if (track.youtube_duration_string) {
          this.totalTime.textContent = track.youtube_duration_string;
        } else {
          this.totalTime.textContent = this.formatTime(duration);
        }
      } else {
        this.progressBar.style.width = '0%';
        this.currentTime.textContent = this.formatTime(displayProgress || 0);
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
    this.updateFollowAudioAfterStatus(status);
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
  
  _restartSyncLoop() {
    if (this.syncInterval) {
      clearInterval(this.syncInterval);
      this.syncInterval = null;
    }
    this.syncInterval = setInterval(() => {
      this.syncStatus();
    }, this._syncMs);
  }

  startSync() {
    console.log('📱 Remote: Starting sync...');

    this.loadPlaylistSources();
    
    this._syncMs = 1000;
    this.syncStatus();
    this._restartSyncLoop();
    
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