// Base Player Module - Shared functionality across all player pages

import { 
  shuffle, smartShuffle, detectChannelGroup, smartChannelShuffle, 
  getGroupPlaybackInfo, orderByPublishDate as utilsOrderByPublishDate, 
  formatTime, updateSpeedDisplay as utilsUpdateSpeedDisplay, 
  showNotification, handleVolumeWheel as utilsHandleVolumeWheel, 
  stopTick as utilsStopTick, stopPlayback as utilsStopPlayback, 
  playIndex as utilsPlayIndex, updateMuteIcon as utilsUpdateMuteIcon, 
  nextTrack as utilsNextTrack, prevTrack as utilsPrevTrack, 
  sendStreamEvent as utilsSendStreamEvent, startTick as utilsStartTick, 
  reportEvent as utilsReportEvent, triggerAutoDeleteCheck as utilsTriggerAutoDeleteCheck, 
  recordSeekEvent, saveVolumeToDatabase as utilsSaveVolumeToDatabase, 
  loadSavedVolume as utilsLoadSavedVolume, performKeyboardSeek as utilsPerformKeyboardSeek, 
  syncLikeButtonsWithRemote as utilsSyncLikeButtonsWithRemote, 
  syncLikesAfterAction as utilsSyncLikesAfterAction, 
  setupLikeSyncHandlers as utilsSetupLikeSyncHandlers, 
  togglePlayback as utilsTogglePlayback, showFsControls as utilsShowFsControls, 
  updateFsVisibility as utilsUpdateFsVisibility, syncRemoteState as utilsSyncRemoteState, 
  setupGlobalTooltip as utilsSetupGlobalTooltip, createTrackTooltipHTML, 
  pollRemoteCommands as utilsPollRemoteCommands, cyclePlaybackSpeed as utilsCyclePlaybackSpeed, 
  executeRemoteCommand as utilsExecuteRemoteCommand, deleteTrack as utilsDeleteTrack, 
  initializeGoogleCastIntegration as utilsInitializeGoogleCastIntegration, 
  castLoad as utilsCastLoad, loadTrack as utilsLoadTrack, 
  setupMediaEndedHandler, setupMediaPlayPauseHandlers, setupMediaTimeUpdateHandler, 
  setupMediaSeekedHandler, setupKeyboardHandler, setupProgressClickHandler, 
  setupMediaSessionAPI, setupPlaylistToggleHandler, setupDeleteCurrentHandler, 
  setupLikeDislikeHandlers, setupYouTubeHandler, setupFullscreenHandlers, 
  setupSimpleControlHandlers, setupStreamHandler, setupBeforeUnloadHandler, 
  setupAutoPlayInitialization, setupRemoteControlOverrides, setupRemoteControlInitialization 
} from '/static/js/modules/index.js';

import { updateCurrentTrackTitle } from '/static/js/modules/track-title-manager.js';

// Base player configuration
export class BasePlayer {
  constructor(config = {}) {
    this.config = {
      isVirtual: false,
      orderByDateSchema: 'regular',
      showCast: true,
      showStream: true,
      ...config
    };
    
    this.media = document.getElementById('player');
    this.listElem = document.getElementById('tracklist');
    this.tracks = [];
    this.queue = [];
    this.currentIndex = -1;
    this.likedCurrent = false;
    this.streamIdLeader = null;
    this.tickTimer = null;
    this.fsTimer = null;
    
    // Speed control
    this.speedOptions = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5];
    this.currentSpeedIndex = 2; // Default to 1x
    
    this.initialize();
  }
  
  async initialize() {
    await this.loadTracks();
    this.setupEventHandlers();
    this.setupControls();
    this.loadSavedVolume();
    
    if (this.config.showCast) {
      utilsInitializeGoogleCastIntegration();
    }
  }
  
  async loadTracks() {
    // Override in subclasses
    throw new Error('loadTracks must be implemented in subclass');
  }
  
  setupEventHandlers() {
    // Media event handlers
    setupMediaEndedHandler(this.media, () => this.nextTrack());
    setupMediaPlayPauseHandlers(this.media, () => this.togglePlayback());
    setupMediaTimeUpdateHandler(this.media, () => this.updateProgress());
    setupMediaSeekedHandler(this.media, () => this.onSeeked());
    
    // Control handlers
    setupKeyboardHandler(this.media, (offset) => this.performKeyboardSeek(offset));
    setupProgressClickHandler(this.progressContainer, (e) => this.onProgressClick(e));
    setupMediaSessionAPI(this.media, this.tracks, this.currentIndex);
    
    // UI handlers
    setupPlaylistToggleHandler();
    setupDeleteCurrentHandler(() => this.deleteCurrentTrack());
    setupLikeDislikeHandlers(
      () => this.likeCurrentTrack(),
      () => this.dislikeCurrentTrack()
    );
    setupYouTubeHandler(() => this.openOnYouTube());
    setupFullscreenHandlers();
    setupSimpleControlHandlers();
    
    if (this.config.showStream) {
      setupStreamHandler(() => this.startStream());
    }
    
    setupBeforeUnloadHandler();
    setupAutoPlayInitialization();
    setupRemoteControlOverrides();
    setupRemoteControlInitialization();
    
    // Like sync handlers
    utilsSetupLikeSyncHandlers();
  }
  
  setupControls() {
    // Shuffle button
    const shuffleBtn = document.getElementById('shuffleBtn');
    if (shuffleBtn) {
      shuffleBtn.addEventListener('click', () => {
        this.queue = shuffle([...this.tracks]);
        this.currentIndex = -1;
        this.renderList();
        showNotification('🔀 Shuffled playlist');
      });
    }
    
    // Smart shuffle button
    const smartShuffleBtn = document.getElementById('smartShuffleBtn');
    if (smartShuffleBtn) {
      smartShuffleBtn.addEventListener('click', () => {
        this.queue = smartShuffle([...this.tracks]);
        this.currentIndex = -1;
        this.renderList();
        showNotification('🧠 Smart shuffle applied');
      });
    }
    
    // Order by date button
    const orderByDateBtn = document.getElementById('orderByDateBtn');
    if (orderByDateBtn) {
      orderByDateBtn.addEventListener('click', () => {
        this.queue = this.orderByPublishDate([...this.tracks]);
        this.currentIndex = -1;
        this.renderList();
        showNotification('📅 Ordered by publish date');
      });
    }
  }
  
  orderByPublishDate(tracks) {
    return utilsOrderByPublishDate(tracks, this.config.orderByDateSchema);
  }
  
  async loadTrack(idx, autoplay = false) {
    if (idx < 0 || idx >= this.queue.length) return;
    
    const track = this.queue[idx];
    this.currentIndex = idx;
    
    // Load track using common utility
    utilsLoadTrack(this.media, track, autoplay);
    
    // Update UI
    this.renderList();
    updateCurrentTrackTitle(track);
    
    // Update delete button tooltip
    const deleteCurrentBtn = document.getElementById('deleteCurrentBtn');
    if (deleteCurrentBtn && deleteCurrentBtn.updateTooltip) {
        deleteCurrentBtn.updateTooltip();
    }
    
    // Sync with remote
    await utilsSyncRemoteState();
  }
  
  playIndex(idx) {
    utilsPlayIndex(idx, this.queue, this.media, this.currentIndex);
    this.currentIndex = idx;
    this.renderList();
  }
  
  nextTrack() {
    utilsNextTrack(this.queue, this.currentIndex, this.media);
    this.currentIndex = (this.currentIndex + 1) % this.queue.length;
    this.renderList();
  }
  
  prevTrack() {
    utilsPrevTrack(this.queue, this.currentIndex, this.media);
    this.currentIndex = this.currentIndex > 0 ? this.currentIndex - 1 : this.queue.length - 1;
    this.renderList();
  }
  
  togglePlayback() {
    utilsTogglePlayback(this.media);
  }
  
  stopPlayback() {
    utilsStopPlayback(this.media);
  }
  
  updateProgress() {
    if (!this.media.duration) return;
    
    const progress = (this.media.currentTime / this.media.duration) * 100;
    const progressBar = document.getElementById('progressBar');
    if (progressBar) {
      progressBar.style.width = progress + '%';
    }
    
    const timeLabel = document.getElementById('timeLabel');
    if (timeLabel) {
      timeLabel.textContent = `${formatTime(this.media.currentTime)} / ${formatTime(this.media.duration)}`;
    }
    
    // Start tick for progress tracking
    if (!this.tickTimer) {
      utilsStartTick();
      this.tickTimer = setInterval(() => {
        utilsStartTick();
      }, 1000);
    }
  }
  
  onSeeked() {
    recordSeekEvent(this.media.currentTime);
  }
  
  performKeyboardSeek(offsetSeconds) {
    utilsPerformKeyboardSeek(this.media, offsetSeconds);
  }
  
  onProgressClick(e) {
    const rect = e.target.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const width = rect.width;
    const percentage = clickX / width;
    this.media.currentTime = percentage * this.media.duration;
  }
  
  async likeCurrentTrack() {
    if (this.currentIndex < 0 || this.currentIndex >= this.queue.length) return;
    
    const track = this.queue[this.currentIndex];
    await utilsSyncLikesAfterAction(track.video_id, 'like');
    this.likedCurrent = true;
    this.updateLikeButtons();
  }
  
  async dislikeCurrentTrack() {
    if (this.currentIndex < 0 || this.currentIndex >= this.queue.length) return;
    
    const track = this.queue[this.currentIndex];
    await utilsSyncLikesAfterAction(track.video_id, 'dislike');
    this.likedCurrent = false;
    this.updateLikeButtons();
  }
  
  updateLikeButtons() {
    const cLike = document.getElementById('cLike');
    const cDislike = document.getElementById('cDislike');
    
    if (cLike) {
      cLike.classList.toggle('like-active', this.likedCurrent);
    }
    if (cDislike) {
      cDislike.classList.toggle('dislike-active', !this.likedCurrent);
    }
  }
  
  openOnYouTube() {
    if (this.currentIndex < 0 || this.currentIndex >= this.queue.length) return;
    
    const track = this.queue[this.currentIndex];
    window.open(`https://youtu.be/${track.video_id}`, '_blank');
  }
  
  async deleteCurrentTrack() {
    if (this.currentIndex < 0 || this.currentIndex >= this.queue.length) return;
    
    const track = this.queue[this.currentIndex];
    const trackIndex = this.currentIndex;
    
    await utilsDeleteTrack(track, trackIndex);
    
    // Remove from queue and tracks
    this.queue.splice(trackIndex, 1);
    this.tracks = this.tracks.filter(t => t.video_id !== track.video_id);
    
    // Adjust current index
    if (this.currentIndex >= this.queue.length) {
      this.currentIndex = this.queue.length - 1;
    }
    
    this.renderList();
  }
  
  async startStream() {
    if (this.currentIndex < 0 || this.currentIndex >= this.queue.length) return;
    
    const track = this.queue[this.currentIndex];
    const payload = {
      action: 'start_stream',
      video_id: track.video_id,
      title: track.name,
      position: this.media.currentTime
    };
    
    await utilsSendStreamEvent(payload);
  }
  
  renderList() {
    if (!this.listElem) return;
    
    this.listElem.innerHTML = '';
    
    this.queue.forEach((track, idx) => {
      const li = document.createElement('li');
      li.textContent = track.name;
      li.className = idx === this.currentIndex ? 'playing' : '';
      li.onclick = () => this.loadTrack(idx, true);
      
      // Add tooltip
      li.title = createTrackTooltipHTML(track);
      
      this.listElem.appendChild(li);
    });
  }
  
  async loadSavedVolume() {
    const volume = await utilsLoadSavedVolume();
    if (volume !== null) {
      this.media.volume = volume;
      this.updateMuteIcon();
    }
  }
  
  updateMuteIcon() {
    utilsUpdateMuteIcon(this.media);
  }
  
  async saveVolumeToDatabase(volume) {
    await utilsSaveVolumeToDatabase(volume);
  }
  
  updateSpeedDisplay() {
    utilsUpdateSpeedDisplay(this.currentSpeedIndex, this.speedOptions);
  }
  
  async cyclePlaybackSpeed() {
    this.currentSpeedIndex = await utilsCyclePlaybackSpeed(this.currentSpeedIndex, this.speedOptions);
    this.updateSpeedDisplay();
  }
  
  showFsControls() {
    utilsShowFsControls();
  }
  
  updateFsVisibility() {
    utilsUpdateFsVisibility();
  }
  
  async syncRemoteState() {
    await utilsSyncRemoteState();
  }
  
  async pollRemoteCommands() {
    await utilsPollRemoteCommands();
  }
  
  async executeRemoteCommand(command) {
    await utilsExecuteRemoteCommand(command);
  }
  
  async syncLikeButtonsWithRemote() {
    await utilsSyncLikeButtonsWithRemote();
  }
  
  destroy() {
    if (this.tickTimer) {
      clearInterval(this.tickTimer);
      utilsStopTick();
    }
  }
}

export default BasePlayer; 