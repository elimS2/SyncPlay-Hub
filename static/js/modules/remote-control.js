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
    /** @type {HTMLMediaElement[]} */
    this.followAudios = [];
    /** @type {HTMLMediaElement[]} */
    this.followVideos = [];
    /** Active slot 0|1 for ping-pong within each kind. */
    this._followAudioSlot = 0;
    this._followVideoSlot = 0;
    /** @type {'audio'|'video'|null} */
    this._followMediaKind = null;
    this._followTrackKey = null;
    this._followLoadPending = false;

    /** NTP-style offset: estimated_server_ms ≈ Date.now() + median offset. */
    this._clockSkewSamples = [];
    this._syncMs = 1000;
    /** Avoid repeated currentTime seeks (causes stutter on mobile). */
    this._followLastHardSeekMs = 0;
    /**
     * Manual pitch mode (toggle): follow sync never changes playbackRate; − / 1× / + / hold only.
     * Cleared when stopping Listen here. Persists across tracks until toggled off.
     */
    this._followDeckManualMode = false;
    /** Locked rate while manual mode is on (source of truth for label + reassert after sync). */
    this._followDeckTargetRate = null;
    /** Hold-to-pause on phone; blocks sync loop from calling play(). */
    this._deckBrakeHeld = false;
    /** After a new src + metadata, skip playbackRate nudge until time settles (avoids instant 1.05). */
    this._followRateNudgeGraceUntilMs = 0;
    /** next_track identity loaded into passive slot (avoid redundant work). */
    this._followPreloadIdentity = null;

    this.micSync =
      typeof RemoteMicSyncController !== 'undefined' ? new RemoteMicSyncController(this) : null;

    /** Only one /remote/status fetch at a time; avoids piling requests and starving POST /like (HTTP/1.1 connection limit). */
    this._statusSyncInFlight = false;
    this._statusSyncQueued = false;
    this._followLoadWatchdogTimer = null;
    /** After server reports a new video_id, use raw progress only (no anchor extrapolation) to avoid post-advance jumps. */
    this._followPostTrackServerGraceUntilMs = 0;

    this.initElements();
    this.attachEvents();
    this.startSync();
    this.updateMicSyncButtons();
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
    this.followAudios = [
      document.getElementById('remoteFollowAudio0'),
      document.getElementById('remoteFollowAudio1'),
    ].filter(Boolean);
    this.followVideos = [
      document.getElementById('remoteFollowVideo0'),
      document.getElementById('remoteFollowVideo1'),
    ].filter(Boolean);

    this.deckSlowerBtn = document.getElementById('deckSlowerBtn');
    this.deckResetBtn = document.getElementById('deckResetBtn');
    this.deckFasterBtn = document.getElementById('deckFasterBtn');
    this.deckBrakeBtn = document.getElementById('deckBrakeBtn');
    this.deckPitchLabel = document.getElementById('deckPitchLabel');
    this.deckManualModeBtn = document.getElementById('deckManualModeBtn');
    this.deckManualModeLabel = document.getElementById('deckManualModeLabel');
    this.deckManualSection = document.getElementById('deckManualSection');
    this.micSyncAutoBtn = document.getElementById('micSyncAutoBtn');
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
      const wasLiked = this.likeBtn.classList.contains('like-active');
      if (!wasLiked) {
        this.likeBtn.classList.add('like-active');
        this.dislikeBtn.classList.remove('dislike-active');
      }
      const ok = await this.sendCommand('like');
      if (!ok && !wasLiked) {
        this.likeBtn.classList.remove('like-active');
      }
    });
    this.dislikeBtn.addEventListener('click', async () => {
      const wasDisliked = this.dislikeBtn.classList.contains('dislike-active');
      if (!wasDisliked) {
        this.dislikeBtn.classList.add('dislike-active');
        this.likeBtn.classList.remove('like-active');
      }
      const ok = await this.sendCommand('dislike');
      if (!ok && !wasDisliked) {
        this.dislikeBtn.classList.remove('dislike-active');
      }
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
    if (this.deckManualModeBtn) {
      this.deckManualModeBtn.addEventListener('click', () => this.toggleDeckManualMode());
    }
    if (this.deckSlowerBtn) {
      this.deckSlowerBtn.addEventListener('click', () => this.nudgeDeckSlower());
    }
    if (this.deckResetBtn) {
      this.deckResetBtn.addEventListener('click', () => this.resetDeckPitch());
    }
    if (this.deckFasterBtn) {
      this.deckFasterBtn.addEventListener('click', () => this.nudgeDeckFaster());
    }
    if (this.deckBrakeBtn) {
      this.deckBrakeBtn.addEventListener('pointerdown', (e) => {
        if (this.deckBrakeBtn.disabled) return;
        e.preventDefault();
        try {
          this.deckBrakeBtn.setPointerCapture(e.pointerId);
        } catch (err) {
          /* ignore */
        }
        this._deckBrakePointerDown();
      });
      this.deckBrakeBtn.addEventListener('pointerup', (e) => {
        try {
          this.deckBrakeBtn.releasePointerCapture(e.pointerId);
        } catch (err) {
          /* ignore */
        }
        this._deckBrakePointerUp();
      });
      this.deckBrakeBtn.addEventListener('pointercancel', () => this._deckBrakePointerUp());
    }
    if (this.micSyncAutoBtn) {
      this.micSyncAutoBtn.addEventListener('click', () => this.runMicSyncAuto());
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
    this.followAudios.forEach((el) => el && el.addEventListener('error', onFollowMediaError));
    this.followVideos.forEach((el) => el && el.addEventListener('error', onFollowMediaError));
  }

  _stopBothFollowMedia() {
    [...this.followAudios, ...this.followVideos].forEach((el) => {
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
    this._followAudioSlot = 0;
    this._followVideoSlot = 0;
    this._followPreloadIdentity = null;
  }

  _clearFollowKind(kind) {
    if (kind !== 'audio' && kind !== 'video') return;
    const list = kind === 'audio' ? this.followAudios : this.followVideos;
    list.forEach((el) => {
      if (!el) return;
      try {
        el.pause();
      } catch (e) {
        /* ignore */
      }
      el.removeAttribute('src');
      try {
        el.load();
      } catch (e) {
        /* ignore */
      }
    });
  }

  _ensureFollowKind(useAudio) {
    const nextKind = useAudio ? 'audio' : 'video';
    if (this._followMediaKind === nextKind) return;
    this._clearFollowKind(this._followMediaKind);
    this._clearFollowKind(nextKind);
    this._followMediaKind = nextKind;
    this._followAudioSlot = 0;
    this._followVideoSlot = 0;
  }

  _followActiveAudioEl() {
    return this.followAudios[this._followAudioSlot] || null;
  }

  _followPassiveAudioEl() {
    return this.followAudios[1 - this._followAudioSlot] || null;
  }

  _followActiveVideoEl() {
    return this.followVideos[this._followVideoSlot] || null;
  }

  _followPassiveVideoEl() {
    return this.followVideos[1 - this._followVideoSlot] || null;
  }

  /**
   * Passive slot holds `next_track` so we can swap to it on advance (stitch).
   * @param {object} status
   */
  _syncFollowNextPreload(status) {
    if (!this.followAudioActive || !status) return;
    const cur = status.current_track;
    const next = status.next_track;
    if (!next) {
      this._followPreloadIdentity = null;
      if (this._followMediaKind === 'audio') {
        const p = this._followPassiveAudioEl();
        if (p && p.src) {
          p.removeAttribute('src');
          try {
            p.load();
          } catch (e) {
            /* ignore */
          }
        }
      } else if (this._followMediaKind === 'video') {
        const p = this._followPassiveVideoEl();
        if (p && p.src) {
          p.removeAttribute('src');
          try {
            p.load();
          } catch (e) {
            /* ignore */
          }
        }
      }
      return;
    }
    const nextUrl = this._buildMediaUrl(next);
    if (!nextUrl) {
      this._followPreloadIdentity = null;
      return;
    }
    const nextId = this._followTrackIdentity(next);
    if (!nextId) return;
    const curId = cur ? this._followTrackIdentity(cur) : null;
    if (curId != null && nextId === curId) return;

    const useAudio = this._isAudioOnlyUrl(nextUrl);
    if (this._followMediaKind !== (useAudio ? 'audio' : 'video')) return;

    const active = useAudio ? this._followActiveAudioEl() : this._followActiveVideoEl();
    const passive = useAudio ? this._followPassiveAudioEl() : this._followPassiveVideoEl();
    if (!passive || !active) return;
    try {
      if (active.src && new URL(active.src).href === new URL(nextUrl).href) return;
    } catch {
      /* continue */
    }

    if (this._followPreloadIdentity === nextId) return;
    this._followPreloadIdentity = nextId;
    try {
      passive.preload = 'auto';
      passive.muted = true;
      passive.defaultPlaybackRate = 1;
      passive.playbackRate = 1;
      passive.src = nextUrl;
      passive.load();
    } catch (e) {
      console.warn('Follow passive preload failed:', e);
    }
  }

  /** @returns {HTMLMediaElement|null} */
  _followActiveMediaEl() {
    if (this._followMediaKind === 'audio') return this._followActiveAudioEl();
    if (this._followMediaKind === 'video') return this._followActiveVideoEl();
    return null;
  }

  /**
   * @param {string} absUrl
   * @returns {HTMLMediaElement|null}
   */
  _mediaElForUrl(absUrl) {
    const useAudio = this._isAudioOnlyUrl(absUrl);
    this._ensureFollowKind(useAudio);
    return useAudio ? this._followActiveAudioEl() : this._followActiveVideoEl();
  }

  /**
   * @param {string} url
   * @returns {boolean}
   */
  _isAudioOnlyUrl(url) {
    const ext = (url.split('?')[0].split('.').pop() || '').toLowerCase();
    return ['mp3', 'm4a', 'aac', 'flac', 'opus', 'ogg', 'oga', 'wav'].includes(ext);
  }

  /** @returns {HTMLMediaElement|null} */
  getFollowPlaybackElement() {
    return this._followActiveMediaEl();
  }

  _followMicSyncPrecheck() {
    if (!this.followAudioActive) {
      const t = window.ToastNotifications && window.ToastNotifications.showToast;
      if (t) {
        t('Turn on Listen here first (local playback is the reference).', { id: 'micSyncNeedFollow' });
      }
      return null;
    }
    const el = this.getFollowPlaybackElement();
    if (!el || !el.src) {
      const t = window.ToastNotifications && window.ToastNotifications.showToast;
      if (t) t('Nothing playing on this device yet.', { id: 'micSyncNoMedia' });
      return null;
    }
    return el;
  }

  updateMicSyncButtons() {
    const can = this.followAudioActive;
    const autoBusy = this.micSync && this.micSync.isAutoRunning();
    const deck = can && this._followDeckManualMode;
    [this.deckSlowerBtn, this.deckResetBtn, this.deckFasterBtn, this.deckBrakeBtn].forEach((b) => {
      if (b) b.disabled = !deck || !!autoBusy;
    });
    if (this.micSyncAutoBtn) {
      this.micSyncAutoBtn.disabled = !can || !!autoBusy;
    }
    if (this.deckManualModeBtn) {
      this.deckManualModeBtn.disabled = !can;
      this.deckManualModeBtn.classList.toggle('active', !!this._followDeckManualMode);
    }
    if (this.deckManualModeLabel) {
      this.deckManualModeLabel.textContent = this._followDeckManualMode ? 'Manual pitch: On' : 'Manual pitch: Off';
    }
    if (this.deckManualSection) {
      this.deckManualSection.hidden = !(can && this._followDeckManualMode);
    }
    this.updateDeckPitchLabel();
  }

  toggleDeckManualMode() {
    if (!this.followAudioActive) return;
    this._followDeckManualMode = !this._followDeckManualMode;
    if (this._followDeckManualMode) {
      this._followDeckTargetRate = 1;
      const el = this.getFollowPlaybackElement();
      if (el && el.src) {
        try {
          el.playbackRate = 1;
        } catch (e) {
          /* ignore */
        }
      }
    } else {
      this._followDeckTargetRate = null;
      this._deckBrakePointerUp();
      const el = this.getFollowPlaybackElement();
      if (el) {
        try {
          el.playbackRate = 1;
        } catch (e) {
          /* ignore */
        }
      }
    }
    this.updateMicSyncButtons();
    if (this.currentStatus) {
      this.updateFollowAudioAfterStatus(this.currentStatus);
    }
  }

  updateDeckPitchLabel() {
    if (!this.deckPitchLabel) return;
    const el = this.getFollowPlaybackElement();
    if (!el || !this.followAudioActive) {
      this.deckPitchLabel.textContent = '1.00×';
      return;
    }
    if (
      this._followDeckManualMode &&
      this._followDeckTargetRate != null &&
      Number.isFinite(this._followDeckTargetRate)
    ) {
      this.deckPitchLabel.textContent = `${this._followDeckTargetRate.toFixed(2)}×`;
      return;
    }
    const r = Number(el.playbackRate);
    const v = Number.isFinite(r) ? r : 1;
    this.deckPitchLabel.textContent = `${v.toFixed(2)}×`;
  }

  /** If sync or the browser touched playbackRate, put back the deck-chosen value. */
  _followReassertManualPlaybackRate(mediaEl) {
    if (!this._followDeckManualMode || !mediaEl) return;
    const want = this._followDeckTargetRate;
    if (want == null || !Number.isFinite(want)) return;
    const cur = Number(mediaEl.playbackRate);
    if (Number.isFinite(cur) && Math.abs(cur - want) <= 0.008) return;
    try {
      mediaEl.playbackRate = want;
    } catch (e) {
      /* ignore */
    }
  }

  nudgeDeckSlower() {
    const el = this._followMicSyncPrecheck();
    if (!el || !this._followDeckManualMode) return;
    const minR = 0.88;
    const step = 0.01;
    let r = Number(el.playbackRate);
    if (!Number.isFinite(r)) r = 1;
    el.playbackRate = Math.max(minR, r - step);
    this._followDeckTargetRate = Number(el.playbackRate);
    this.updateDeckPitchLabel();
  }

  nudgeDeckFaster() {
    const el = this._followMicSyncPrecheck();
    if (!el || !this._followDeckManualMode) return;
    const maxR = 1.12;
    const step = 0.01;
    let r = Number(el.playbackRate);
    if (!Number.isFinite(r)) r = 1;
    el.playbackRate = Math.min(maxR, r + step);
    this._followDeckTargetRate = Number(el.playbackRate);
    this.updateDeckPitchLabel();
  }

  resetDeckPitch() {
    const el = this._followMicSyncPrecheck();
    if (!el || !this._followDeckManualMode) return;
    this._followDeckTargetRate = 1;
    el.playbackRate = 1;
    this.updateDeckPitchLabel();
    const t = window.ToastNotifications && window.ToastNotifications.showToast;
    if (t) t('Speed set to 1.00×', { id: 'deckResetToast', duration: 1600 });
  }

  _deckBrakePointerDown() {
    const el = this.getFollowPlaybackElement();
    if (!el || !this.followAudioActive || !this._followDeckManualMode) return;
    this._deckBrakeHeld = true;
    try {
      el.pause();
    } catch (e) {
      /* ignore */
    }
  }

  _deckBrakePointerUp() {
    if (!this._deckBrakeHeld) return;
    this._deckBrakeHeld = false;
    const el = this.getFollowPlaybackElement();
    if (!el) return;
    if (this.currentStatus && this.currentStatus.playing) {
      el.play().catch(() => {});
    }
  }

  runMicSyncAuto() {
    if (!this.micSync) return;
    const el = this._followMicSyncPrecheck();
    if (!el) return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      const t = window.ToastNotifications && window.ToastNotifications.showToast;
      if (t) {
        t(
          !window.isSecureContext
            ? 'Microphone needs HTTPS (or localhost). Open the remote page over a secure connection.'
            : 'Microphone not available in this browser.',
          { id: 'micSyncToast', backgroundColor: 'rgba(139, 0, 0, 0.92)', duration: 5000 },
        );
      }
      return;
    }
    this.updateMicSyncButtons();
    // getUserMedia must run in the same synchronous turn as the click; do not await before it.
    navigator.mediaDevices
      .getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
        video: false,
      })
      .then((stream) => this.micSync.runAutoWithMicStream(el, stream))
      .catch((e) => {
        console.warn('Mic sync getUserMedia failed:', e);
        const t = window.ToastNotifications && window.ToastNotifications.showToast;
        if (t) {
          t(
            'Microphone was blocked or unavailable. Allow microphone for this site in the browser address bar, then try again.',
            { id: 'micSyncToast', backgroundColor: 'rgba(139, 0, 0, 0.92)', duration: 5500 },
          );
        }
      })
      .finally(() => this.updateMicSyncButtons());
  }

  toggleFollowAudio() {
    this.followAudioActive = !this.followAudioActive;
    this.updateFollowAudioButton();
    if (!this.followAudioActive) {
      this._deckBrakePointerUp();
      if (this.micSync) {
        void this.micSync.stopAll();
      }
      if (this._followLoadWatchdogTimer != null) {
        clearTimeout(this._followLoadWatchdogTimer);
        this._followLoadWatchdogTimer = null;
      }
      this._followTrackKey = null;
      this._followLoadPending = false;
      this._followMediaKind = null;
      this._followDeckManualMode = false;
      this._followDeckTargetRate = null;
      this._stopBothFollowMedia();
      this._syncMs = 1000;
      this._restartSyncLoop();
      this.updateMicSyncButtons();
      return;
    }
    if (this.currentStatus) {
      this.updateFollowAudioAfterStatus(this.currentStatus);
    }
    this._syncMs = 400;
    this._restartSyncLoop();
    this.syncStatus();
    this.updateMicSyncButtons();
  }

  updateFollowAudioButton() {
    if (!this.followAudioBtn || !this.followAudioLabel) return;
    this.followAudioBtn.classList.toggle('active', this.followAudioActive);
    this.followAudioLabel.textContent = this.followAudioActive ? 'Stop local audio' : 'Listen here';
    this.followAudioBtn.title = this.followAudioActive
      ? 'Stop playback on this phone'
      : 'Play the same track on this phone (for another room). One tap unlocks audio in the browser.';
    this.updateMicSyncButtons();
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
    const raw = Math.max(0, Number(status.progress) || 0);
    if (Date.now() < (this._followPostTrackServerGraceUntilMs || 0)) {
      return raw;
    }
    const anchorMs = status.playback_anchor_server_ms;
    const pos = status.playback_anchor_position;
    const playing = status.playback_anchor_playing;
    const anchorKey = status.playback_anchor_track_key;
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
    if (this._followDeckManualMode) return;
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
      this._followRateNudgeGraceUntilMs = 0;
      if (!this._followDeckManualMode) {
        this._followDeckTargetRate = null;
      }
      this._stopBothFollowMedia();
      return;
    }

    const key = this._followTrackIdentity(track);
    const useAudio = this._isAudioOnlyUrl(absUrl);

    if (this._followTrackKey !== key) {
      if (this._followLoadWatchdogTimer != null) {
        clearTimeout(this._followLoadWatchdogTimer);
        this._followLoadWatchdogTimer = null;
      }
      this._followTrackKey = key;
      this._followLoadPending = true;
      this._followLastHardSeekMs = 0;
      this._ensureFollowKind(useAudio);

      const pinnedRate =
        this._followDeckManualMode &&
        this._followDeckTargetRate != null &&
        Number.isFinite(this._followDeckTargetRate)
          ? this._followDeckTargetRate
          : 1;

      const passive = useAudio ? this._followPassiveAudioEl() : this._followPassiveVideoEl();
      let mediaEl = useAudio ? this._followActiveAudioEl() : this._followActiveVideoEl();
      let stitched = false;

      try {
        const want = new URL(absUrl).href;
        if (
          passive &&
          passive.src &&
          new URL(passive.src).href === want &&
          passive.readyState >= 2
        ) {
          if (useAudio) this._followAudioSlot = 1 - this._followAudioSlot;
          else this._followVideoSlot = 1 - this._followVideoSlot;
          stitched = true;
          mediaEl = useAudio ? this._followActiveAudioEl() : this._followActiveVideoEl();
          const oldEl = useAudio ? this._followPassiveAudioEl() : this._followPassiveVideoEl();
          if (oldEl) {
            oldEl.pause();
            oldEl.removeAttribute('src');
            try {
              oldEl.load();
            } catch (e) {
              /* ignore */
            }
          }
        }
      } catch (e) {
        /* cold load */
      }

      if (!stitched) {
        mediaEl = useAudio ? this._followActiveAudioEl() : this._followActiveVideoEl();
        if (!mediaEl) {
          this._syncFollowNextPreload(status);
          return;
        }
        mediaEl.playbackRate = pinnedRate;
        mediaEl.src = absUrl;
      } else if (mediaEl) {
        mediaEl.playbackRate = pinnedRate;
      }

      if (!mediaEl) {
        this._syncFollowNextPreload(status);
        return;
      }

      if (mediaEl.tagName === 'VIDEO') {
        mediaEl.setAttribute('playsinline', '');
        mediaEl.playsInline = true;
      }

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
      const clearLoadWatchdog = () => {
        if (this._followLoadWatchdogTimer != null) {
          clearTimeout(this._followLoadWatchdogTimer);
          this._followLoadWatchdogTimer = null;
        }
      };
      this._followLoadWatchdogTimer = window.setTimeout(() => {
        this._followLoadWatchdogTimer = null;
        if (this._followTrackKey === expectedKey && this._followLoadPending) {
          console.warn('Follow-media: load watchdog cleared stuck _followLoadPending');
          this._followLoadPending = false;
        }
      }, 20000);
      const onMeta = () => {
        if (metaApplied) return;
        if (!this.followAudioActive) {
          clearLoadWatchdog();
          this._followLoadPending = false;
          return;
        }
        if (this._followTrackKey !== expectedKey) {
          clearLoadWatchdog();
          this._followLoadPending = false;
          return;
        }
        metaApplied = true;
        clearLoadWatchdog();
        this._followLoadPending = false;
        const st = this.currentStatus || status;
        const pos = this._expectedProgressSec(st);
        try {
          mediaEl.currentTime = pos;
        } catch (e) {
          console.warn('Follow-media seek failed:', e);
        }
        this._applyFollowVolumeFromStatus(st, mediaEl);
        // Do not stomp a deck reset / nudge that happened while load was pending (onMeta runs later).
        const deckLocked = this._followDeckManualMode;
        if (!deckLocked) {
          this._followDeckTargetRate = null;
          mediaEl.playbackRate = 1;
        } else {
          const want = this._followDeckTargetRate;
          if (want != null && Number.isFinite(want)) {
            try {
              mediaEl.playbackRate = want;
            } catch (e) {
              /* ignore */
            }
          }
          const tr = Number(mediaEl.playbackRate);
          this._followDeckTargetRate = Number.isFinite(tr) ? tr : 1;
        }
        this.updateDeckPitchLabel();
        mediaEl.muted = false;
        if (st.playing) {
          mediaEl.play().catch((err) => console.warn('Follow-media play failed:', err));
        } else {
          mediaEl.pause();
        }
        // Until the element catches up after initial seek, delta is often inflated → spurious +0.05 nudge.
        this._followRateNudgeGraceUntilMs = Date.now() + 5000;
      };

      const onFollowLoadError = () => {
        mediaEl.removeEventListener('error', onFollowLoadError);
        clearLoadWatchdog();
        if (this._followTrackKey === expectedKey) {
          this._followLoadPending = false;
        }
      };
      mediaEl.addEventListener('error', onFollowLoadError, { once: true });
      mediaEl.addEventListener('loadedmetadata', onMeta, { once: true });
      if (mediaEl.readyState >= 1) {
        queueMicrotask(() => onMeta());
      }
      this._syncFollowNextPreload(status);
      return;
    }

    const mediaEl = this._mediaElForUrl(absUrl);
    if (!mediaEl) return;
    if (mediaEl.tagName === 'VIDEO') {
      mediaEl.setAttribute('playsinline', '');
      mediaEl.playsInline = true;
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

    const inServerTrackGrace = Date.now() < (this._followPostTrackServerGraceUntilMs || 0);

    if (status.playing) {
      const sinceSeek = now - this._followLastHardSeekMs;
      const doHardSeek =
        !inServerTrackGrace &&
        (drift >= emergencySeekDrift ||
          (drift >= hardSeekDrift && sinceSeek >= hardSeekCooldownMs));

      if (doHardSeek) {
        try {
          if (!this._followDeckManualMode) {
            mediaEl.playbackRate = 1;
          }
          mediaEl.currentTime = Math.max(0, target);
          this._followLastHardSeekMs = now;
          if (!this._followDeckManualMode) {
            mediaEl.playbackRate = 1;
          }
          this._followReassertManualPlaybackRate(mediaEl);
          this.updateDeckPitchLabel();
        } catch (e) {
          console.warn('Follow-media resync seek failed:', e);
        }
      } else if (
        !inServerTrackGrace &&
        !this._followDeckManualMode &&
        now >= this._followRateNudgeGraceUntilMs
      ) {
        this._followNudgePlaybackRate(mediaEl, delta);
      }
      if (mediaEl.paused && !this._deckBrakeHeld) {
        mediaEl.muted = false;
        mediaEl.play().catch((err) => console.warn('Follow-media play failed:', err));
      }
    } else {
      mediaEl.pause();
      if (!this._followDeckManualMode) {
        mediaEl.playbackRate = 1;
        this.updateDeckPitchLabel();
      }
      if (drift > 2.5) {
        try {
          mediaEl.currentTime = Math.max(0, target);
        } catch (e) {
          console.warn('Follow-media pause seek failed:', e);
        }
      }
    }
    this._followReassertManualPlaybackRate(mediaEl);
    this.updateDeckPitchLabel();
    this._syncFollowNextPreload(status);
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
        void this.syncStatus();
        return true;
      }
      console.error(`Failed to send command ${command}`);
      return false;
    } catch (error) {
      console.error(`Error sending command ${command}:`, error);
      this.updateConnectionStatus(false);
      return false;
    }
  }
  
  async syncStatus() {
    if (this._statusSyncInFlight) {
      this._statusSyncQueued = true;
      return;
    }
    this._statusSyncInFlight = true;
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
    } finally {
      this._statusSyncInFlight = false;
      if (this._statusSyncQueued) {
        this._statusSyncQueued = false;
        void this.syncStatus();
      }
    }
  }
  
  updateStatus(status) {
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
      if (this.followAudioActive) {
        this._followPostTrackServerGraceUntilMs = Date.now() + 7000;
        this._followLastHardSeekMs = 0;
      }
    }

    // PLAYER_STATE.like_active may still be from the *previous* track for one poll after advance;
    // re-applying it here would undo the reset above. Skip one cycle when video_id actually changed.
    const skipReactionFromServer =
      prevVideoId !== null && nextVideoId !== null && prevVideoId !== nextVideoId;

    const applySessionReactionFromStatus = () => {
      if (skipReactionFromServer) return;
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
    };

    const vid =
      nextVideoId != null && nextVideoId !== '' ? String(nextVideoId) : null;
    const sinceMs = status.playback_session_started_ms;
    if (
      vid &&
      typeof sinceMs === 'number' &&
      sinceMs > 0 &&
      !Number.isNaN(sinceMs)
    ) {
      fetch(`/api/reaction/${encodeURIComponent(vid)}?since_ms=${Math.round(sinceMs)}`)
        .then((r) => (r.ok ? r.json() : Promise.resolve({})))
        .then((data) => {
          const cur = this.currentTrack?.video_id;
          if (cur == null || String(cur) !== vid) return;
          const sessionReaction =
            data.status === 'ok' && (data.reaction === 'like' || data.reaction === 'dislike')
              ? data.reaction
              : null;
          if (sessionReaction === 'like') {
            this.likeBtn.classList.add('like-active');
            this.dislikeBtn.classList.remove('dislike-active');
            return;
          }
          if (sessionReaction === 'dislike') {
            this.dislikeBtn.classList.add('dislike-active');
            this.likeBtn.classList.remove('like-active');
            return;
          }
          applySessionReactionFromStatus();
        })
        .catch(() => {
          applySessionReactionFromStatus();
        });
    } else {
      applySessionReactionFromStatus();
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