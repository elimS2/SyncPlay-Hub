async function fetchTracks(playlistPath = '') {
  const endpoint = playlistPath ? `/api/tracks/${encodeURI(playlistPath)}` : '/api/tracks';
  const res = await fetch(endpoint);
  return await res.json();
}

function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
}

(async () => {
  const media = document.getElementById('player');
  const listElem = document.getElementById('tracklist');
  const shuffleBtn = document.getElementById('shuffleBtn');
  const smartShuffleBtn = document.getElementById('smartShuffleBtn');
  const stopBtn = document.getElementById('stopBtn');
  const nextBtn = document.getElementById('nextBtn');
  const prevBtn = document.getElementById('prevBtn');
  const playBtn = document.getElementById('playBtn');
  const fullBtn = document.getElementById('fullBtn');
  const cLike = document.getElementById('cLike');
  const cYoutube = document.getElementById('cYoutube');
  let likedCurrent = false;
  const wrapper = document.getElementById('videoWrapper');
  const cPrev = document.getElementById('cPrev');
  const cPlay = document.getElementById('cPlay');
  const cNext = document.getElementById('cNext');
  const cFull = document.getElementById('cFull');
  const progressContainer = document.getElementById('progressContainer');
  const progressBar = document.getElementById('progressBar');
  const timeLabel = document.getElementById('timeLabel');
  const cMute = document.getElementById('cMute');
  const cVol = document.getElementById('cVol');
  const toggleListBtn = document.getElementById('toggleListBtn');
  const playlistPanel = document.getElementById('playlistPanel');
  const controlBar = document.getElementById('controlBar');
  const customControls = document.getElementById('customControls');
  let fsTimer;
  const streamBtn = document.getElementById('streamBtn');
  let streamIdLeader = null;
  let tickTimer=null;

  const playlistRel = typeof PLAYLIST_REL !== 'undefined' ? PLAYLIST_REL : '';
  let tracks = await fetchTracks(playlistRel);

  function smartShuffle(list){
     const now = new Date();
     const group1=[];const group2=[];const group3=[];const group4=[];const group5=[];const group6=[];

     const getWeekOfYear=(d)=>{
       const onejan=new Date(d.getFullYear(),0,1);
       return Math.ceil((((d - onejan)/86400000)+onejan.getDay()+1)/7);
     };

     for(const t of list){
        if(!t.last_play){group1.push(t);continue;}
        const tsStr = t.last_play.replace(' ', 'T')+'Z';
        const ts=new Date(tsStr);
        if(ts.getFullYear()<now.getFullYear()){group2.push(t);continue;}
        if(ts.getMonth()<now.getMonth()){group3.push(t);continue;}
        if(getWeekOfYear(ts)<getWeekOfYear(now)){group4.push(t);continue;}
        if(ts.getDate()<now.getDate()){group5.push(t);continue;}
        group6.push(t);
     }

     const all=[group1,group2,group3,group4,group5,group6].flatMap(arr=>{shuffle(arr);return arr;});
     return all;
  }

  let queue = smartShuffle([...tracks]);
  let currentIndex = -1;

  // ---- Google Cast Integration ----
  console.log('🔄 CAST DEBUG: Starting Google Cast integration setup...');
  
  let castContext = null;
  let pendingCastTrack=null;

  // Step 1: Check if Cast button element exists in DOM
  console.log('🔍 CAST DEBUG: Step 1 - Looking for Cast button element...');
  const castBtn = document.getElementById('castBtn');
  if(castBtn){
      console.log('✅ CAST DEBUG: Cast button element found!', castBtn);
      castBtn.style.display='inline-flex';
      console.log('✅ CAST DEBUG: Cast button made visible with display: inline-flex');
      
      // Add click handler for cast button
      castBtn.onclick = () => {
          console.log('🔘 CAST DEBUG: Cast button clicked!');
          if(!castContext) {
              console.warn('❌ CAST DEBUG: Cast context not available when button clicked');
              return;
          }
          
          console.log('🔄 CAST DEBUG: Checking current cast session...');
          const currentSession = castContext.getCurrentSession();
          if(currentSession) {
              console.log('🛑 CAST DEBUG: Active session found, ending it...');
              currentSession.endSession(false);
              console.log('✅ CAST DEBUG: Cast session ended');
          } else {
              console.log('🚀 CAST DEBUG: No active session, requesting new session...');
              castContext.requestSession().then(() => {
                  console.log('✅ CAST DEBUG: Cast session started successfully!');
                  // Load current track if available
                  if(currentIndex >= 0 && currentIndex < queue.length) {
                      console.log('🎵 CAST DEBUG: Loading current track to cast device...');
                      castLoad(queue[currentIndex]);
                  } else {
                      console.log('ℹ️ CAST DEBUG: No current track to load');
                  }
              }).catch(err => {
                  console.warn('❌ CAST DEBUG: Cast session failed:', err);
              });
          }
      };
      console.log('✅ CAST DEBUG: Click handler attached to Cast button');
  }else{
      console.error('❌ CAST DEBUG: Cast button element NOT FOUND in DOM!');
      console.log('🔍 CAST DEBUG: Available button elements:', 
          Array.from(document.querySelectorAll('button')).map(btn => btn.id || btn.className));
  }

  // Step 2: Set up Cast API callback
  console.log('🔄 CAST DEBUG: Step 2 - Setting up Cast API availability callback...');
  window.__onGCastApiAvailable = function(isAvailable){
      console.log('📡 CAST DEBUG: Cast API callback triggered, isAvailable=', isAvailable);
      
      if(isAvailable){
          console.log('✅ CAST DEBUG: Cast API is available, initializing...');
          try {
              console.log('🔄 CAST DEBUG: Getting Cast context instance...');
              castContext = cast.framework.CastContext.getInstance();
              console.log('✅ CAST DEBUG: Cast context obtained:', castContext);
              
              console.log('🔄 CAST DEBUG: Setting Cast context options...');
              castContext.setOptions({
                  receiverApplicationId: chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
                  autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED
              });
              console.log('✅ CAST DEBUG: Cast context options set successfully');
              
              // Double-check button visibility after API load
              const castBtn = document.getElementById('castBtn');
              if(castBtn){
                  castBtn.style.display='inline-flex';
                  castBtn.style.visibility='visible';
                  console.log('✅ CAST DEBUG: Cast button double-checked and made visible after API load');
                  console.log('🎯 CAST DEBUG: Cast button final styles:', {
                      display: castBtn.style.display,
                      visibility: castBtn.style.visibility,
                      offsetWidth: castBtn.offsetWidth,
                      offsetHeight: castBtn.offsetHeight
                  });
              }else{
                  console.error('❌ CAST DEBUG: Cast button element NOT FOUND after API load!');
              }
              
              // Set up session state change listener
              console.log('🔄 CAST DEBUG: Setting up session state change listener...');
              castContext.addEventListener(cast.framework.CastContextEventType.SESSION_STATE_CHANGED, (e) => {
                  console.log('🔄 CAST DEBUG: Session state changed:', e.sessionState);
                  if((e.sessionState === cast.framework.SessionState.SESSION_STARTED || 
                      e.sessionState === cast.framework.SessionState.SESSION_RESUMED) && pendingCastTrack){
                      console.log('🎵 CAST DEBUG: Loading pending track after session start...');
                      castLoad(pendingCastTrack);
                      pendingCastTrack = null;
                  }
              });
              console.log('✅ CAST DEBUG: Session state change listener attached');
              
              console.log('🎉 CAST DEBUG: Google Cast integration fully initialized!');
              
          } catch (error) {
              console.error('❌ CAST DEBUG: Error initializing Cast API:', error);
              console.error('❌ CAST DEBUG: Error stack:', error.stack);
          }
      } else {
          console.warn('❌ CAST DEBUG: Cast API is NOT available');
          console.log('ℹ️ CAST DEBUG: Possible reasons: no Cast devices, API blocked, network issues');
      }
  };
  
  console.log('✅ CAST DEBUG: Cast API callback function set up successfully');

  function castLoad(track){
      console.log('🎵 CAST DEBUG: castLoad() called for track:', track.name);
      
      if(!castContext) {
          console.warn('❌ CAST DEBUG: No cast context available for loading track');
          return;
      }
      
      console.log('🔄 CAST DEBUG: Getting current cast session...');
      const session = castContext.getCurrentSession();
      if(!session){
          console.log('📝 CAST DEBUG: No active session, saving track as pending');
          pendingCastTrack=track;
          return;
      }
      
      console.log('✅ CAST DEBUG: Active cast session found, preparing media...');
      let absUrl = new URL(track.url, window.location.href).href;
      console.log('🔗 CAST DEBUG: Original URL:', track.url);
      console.log('🔗 CAST DEBUG: Absolute URL:', absUrl);
      
      // if hostname is localhost, replace with current local IP (taken from location)
      if (absUrl.includes('localhost')) {
          console.log('🔄 CAST DEBUG: Localhost detected, replacing with server IP...');
          if (typeof SERVER_IP !== 'undefined' && SERVER_IP) {
              absUrl = absUrl.replace('localhost', SERVER_IP);
              console.log('✅ CAST DEBUG: Replaced with SERVER_IP:', SERVER_IP);
          } else {
              absUrl = absUrl.replace('localhost', window.location.hostname);
              console.log('✅ CAST DEBUG: Replaced with hostname:', window.location.hostname);
          }
          console.log('🔗 CAST DEBUG: Final URL for casting:', absUrl);
      }
      
      const ext = absUrl.split('.').pop().toLowerCase();
      const mimeMap = {mp4:'video/mp4', webm:'video/webm', mkv:'video/x-matroska', mov:'video/quicktime', mp3:'audio/mpeg', m4a:'audio/mp4', opus:'audio/ogg', flac:'audio/flac'};
      const mime = mimeMap[ext] || 'video/mp4';
      console.log('🎬 CAST DEBUG: File extension:', ext, 'MIME type:', mime);
      
      console.log('🔄 CAST DEBUG: Creating media info object...');
      const mediaInfo = new chrome.cast.media.MediaInfo(absUrl, mime);
      mediaInfo.metadata = new chrome.cast.media.GenericMediaMetadata();
      mediaInfo.metadata.title = track.name;
      console.log('📝 CAST DEBUG: Media info created:', {
          contentId: mediaInfo.contentId,
          contentType: mediaInfo.contentType,
          title: mediaInfo.metadata.title
      });
      
      console.log('🚀 CAST DEBUG: Sending load request to cast device...');
      const request = new chrome.cast.media.LoadRequest(mediaInfo);
      session.loadMedia(request)
          .then(() => {
              console.log('✅ CAST DEBUG: Media loaded successfully on cast device!');
          })
          .catch(error => {
              console.error('❌ CAST DEBUG: Failed to load media on cast device:', error);
          });
  }

  if(window.cast && castContext){
      castContext.addEventListener(cast.framework.CastContextEventType.SESSION_STATE_CHANGED, (e)=>{
          if((e.sessionState===cast.framework.SessionState.SESSION_STARTED || e.sessionState===cast.framework.SessionState.SESSION_RESUMED) && pendingCastTrack){
              castLoad(pendingCastTrack);
              pendingCastTrack=null;
          }
      });
  }

  function renderList() {
    listElem.innerHTML = '';
    queue.forEach((t, idx) => {
      const li = document.createElement('li');
      // Remove trailing [hash] part from display
      const displayName = t.name.replace(/\s*\[.*?\]$/, '');
      li.textContent = `${idx + 1}. ${displayName}`;
      li.dataset.index = idx;
      if (idx === currentIndex) li.classList.add('playing');
      li.onclick = () => playIndex(idx);
      listElem.appendChild(li);
    });
  }

  function loadTrack(idx, autoplay=false){
    if(idx<0 || idx>=queue.length) return;
    currentIndex=idx;
    const track=queue[currentIndex];
    media.src=track.url;
    if(autoplay){media.play();}else{media.load();}
    if('mediaSession' in navigator){
        navigator.mediaSession.metadata = new MediaMetadata({
            title: track.name,
            artist: '',
            album: '',
        });
    }
    castLoad(track);
    renderList();
    // reset like state visual
    likedCurrent=false;
    cLike.classList.remove('like-active');
    cLike.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>';
    // report play start once per track
    reportEvent(track.video_id, 'start');
    sendStreamEvent({action:'seek', idx: currentIndex, paused: media.paused, position: media.currentTime});
  }

  function playIndex(idx){
    loadTrack(idx,true);
  }

  media.addEventListener('ended', () => {
    // capture current track before any change
    const finishedTrack = queue[currentIndex];

    // report finish first
    if (finishedTrack) {
      reportEvent(finishedTrack.video_id, 'finish');
    }

    // then move to next track if available
    if (currentIndex + 1 < queue.length) {
      playIndex(currentIndex + 1);
    }
  });

  shuffleBtn.onclick = () => {
    queue = [...tracks];
    shuffle(queue);
    playIndex(0);
  };

  smartShuffleBtn.onclick = ()=>{
     queue = smartShuffle([...tracks]);
     playIndex(0);
  };

  stopBtn.onclick = () => {
    media.pause();
    media.currentTime = 0;
  };

  nextBtn.onclick = () => {
    if (currentIndex + 1 < queue.length) {
      // send event for current track before switching
      if(currentIndex>=0){ reportEvent(queue[currentIndex].video_id,'next'); }
      playIndex(currentIndex + 1);
      sendStreamEvent({action:'next', idx: currentIndex, paused: media.paused, position:0});
    }
  };

  prevBtn.onclick = () => {
    if (currentIndex - 1 >= 0) {
      if(currentIndex>=0){ reportEvent(queue[currentIndex].video_id,'prev'); }
      playIndex(currentIndex - 1);
      sendStreamEvent({action:'prev', idx: currentIndex, paused: media.paused, position: media.currentTime});
    }
  };

  playBtn.onclick = () => {
    if (media.paused) {
      media.play();
      sendStreamEvent({action:'play', position: media.currentTime, paused:false});
      startTick();
    } else {
      media.pause();
      sendStreamEvent({action:'pause', position: media.currentTime, paused:true});
    }
  };

  fullBtn.onclick = () => {
    if (!document.fullscreenElement) {
      wrapper.requestFullscreen?.() || wrapper.webkitRequestFullscreen?.();
    } else {
      document.exitFullscreen?.() || document.webkitExitFullscreen?.();
    }
  };

  cPrev.onclick = () => prevBtn.click();
  cNext.onclick = () => nextBtn.click();

  function togglePlay() {
    if (media.paused) {
      media.play();
    } else {
      media.pause();
    }
  }
  cPlay.onclick = togglePlay;

  media.addEventListener('play', () => {
    // Change to pause icon
    cPlay.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
    // Report play/resume event with current position
    if(currentIndex >= 0 && currentIndex < queue.length) {
      const track = queue[currentIndex];
      reportEvent(track.video_id, 'play', media.currentTime);
    }
  });
  media.addEventListener('pause', () => {
    // Change to play icon
    cPlay.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
    // Report pause event with current position
    if(currentIndex >= 0 && currentIndex < queue.length) {
      const track = queue[currentIndex];
      reportEvent(track.video_id, 'pause', media.currentTime);
    }
  });

  function formatTime(s) {
    if (!isFinite(s)) return '0:00';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60).toString().padStart(2, '0');
    return `${m}:${sec}`;
  }

  media.addEventListener('timeupdate', () => {
    const percent = (media.currentTime / media.duration) * 100;
    progressBar.style.width = `${percent}%`;
    timeLabel.textContent = `${formatTime(media.currentTime)} / ${formatTime(media.duration)}`;
  });

  progressContainer.onclick = (e) => {
    const rect = progressContainer.getBoundingClientRect();
    const pos = (e.clientX - rect.left) / rect.width;
    media.currentTime = pos * media.duration;
    sendStreamEvent({action:'seek', idx: currentIndex, paused: media.paused, position: media.currentTime});
  };

  cFull.onclick = () => {
    if (!document.fullscreenElement) {
      wrapper.requestFullscreen?.() || wrapper.webkitRequestFullscreen?.();
    } else {
      document.exitFullscreen?.() || document.webkitExitFullscreen?.();
    }
  };

  // Volume logic
  cMute.onclick = () => {
    media.muted = !media.muted;
    updateMuteIcon();
  };
  cVol.oninput = () => {
    media.volume = parseFloat(cVol.value);
    media.muted = media.volume === 0;
    updateMuteIcon();
    saveVolumeToDatabase(media.volume);
  };
  
  function updateMuteIcon() {
    if (media.muted || media.volume === 0) {
      cMute.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg>';
    } else {
      cMute.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/></svg>';
    }
  }
  
  // Save volume to database with debouncing
  let volumeSaveTimeout = null;
  async function saveVolumeToDatabase(volume) {
    clearTimeout(volumeSaveTimeout);
    volumeSaveTimeout = setTimeout(async () => {
      try {
        await fetch('/api/volume/set', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ volume: volume })
        });
        console.log(`💾 Volume saved: ${Math.round(volume * 100)}%`);
      } catch (error) {
        console.warn('⚠️ Failed to save volume:', error);
      }
    }, 500); // Debounce by 500ms to avoid excessive API calls
  }

  // Load saved volume on page load
  async function loadSavedVolume() {
    try {
      const response = await fetch('/api/volume/get');
      const data = await response.json();
      
      if (data.volume !== undefined) {
        media.volume = data.volume;
        cVol.value = data.volume;
        console.log(`🔊 Loaded saved volume: ${data.volume_percent}%`);
      } else {
        // Default volume if no saved setting
        media.volume = 1.0;
        cVol.value = 1.0;
        console.log('🔊 Using default volume: 100%');
      }
    } catch (error) {
      console.warn('⚠️ Failed to load saved volume, using default:', error);
      media.volume = 1.0;
      cVol.value = 1.0;
    }
    
    updateMuteIcon();
  }
  
  // Load saved volume immediately
  loadSavedVolume();

  // auto smart-shuffle and start playback on first load
  if (queue.length > 0) {
      playIndex(0);
      // Force sync after initial load
      setTimeout(syncRemoteState, 500);
  } else {
      renderList();
  }

  // Keyboard shortcuts: ← prev, → next, Space play/pause
  document.addEventListener('keydown', (e) => {
    switch (e.code) {
      case 'ArrowRight':
        nextBtn.click();
        break;
      case 'ArrowLeft':
        prevBtn.click();
        break;
      case 'Space':
        e.preventDefault();
        playBtn.click();
        break;
    }
  });

  function showFsControls(){
     if(!document.fullscreenElement) return;
     customControls.classList.remove('hidden');
     controlBar.classList.remove('hidden');
     clearTimeout(fsTimer);
     fsTimer = setTimeout(()=>{
        if(document.fullscreenElement){
           customControls.classList.add('hidden');
           controlBar.classList.add('hidden');
        }
     },3000);
  }

  function updateFsVisibility(){
     if(document.fullscreenElement){
        listElem.style.display='none';
        showFsControls();
        // mouse move to reveal controls
        wrapper.addEventListener('mousemove', showFsControls);
     }else{
        listElem.style.display='';
        customControls.classList.remove('hidden');
        controlBar.classList.remove('hidden');
        wrapper.removeEventListener('mousemove', showFsControls);
        clearTimeout(fsTimer);
     }
  }
  document.addEventListener('fullscreenchange', updateFsVisibility);
  updateFsVisibility();

  // ---- Media Session API ----
  if ('mediaSession' in navigator) {
      navigator.mediaSession.setActionHandler('previoustrack', () => prevBtn.click());
      navigator.mediaSession.setActionHandler('nexttrack', () => nextBtn.click());
      navigator.mediaSession.setActionHandler('play', () => media.play());
      navigator.mediaSession.setActionHandler('pause', () => media.pause());
  }

  // Clicking on the video toggles play/pause
  media.addEventListener('click', togglePlay);

  // Playlist collapse/expand
  toggleListBtn.onclick = () => {
      playlistPanel.classList.toggle('collapsed');
      toggleListBtn.textContent = playlistPanel.classList.contains('collapsed') ? '☰ Show playlist' : '☰ Hide playlist';
  };

  cLike.onclick = ()=>{
     if(currentIndex<0||currentIndex>=queue.length) return;
     const track=queue[currentIndex];
     reportEvent(track.video_id,'like', media.currentTime);
     likedCurrent = true;
     cLike.classList.add('like-active');
     // Change to filled heart
     cLike.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>';
  };

  cYoutube.onclick = ()=>{
     if(currentIndex<0||currentIndex>=queue.length) return;
     const track=queue[currentIndex];
     if(track.video_id){
        const youtubeUrl = `https://www.youtube.com/watch?v=${track.video_id}`;
        window.open(youtubeUrl, '_blank');
     }else{
        console.warn('No video_id found for current track');
     }
  };

  async function reportEvent(videoId, event, position=null){
     if(!videoId) return;
     try{
        await fetch('/api/event', {
           method:'POST',
           headers:{'Content-Type':'application/json'},
           body: JSON.stringify({video_id: videoId, event, position})
        });
     }catch(err){
        console.warn('event report failed', err);
     }
  }

  async function sendStreamEvent(payload){
     if(!streamIdLeader) return;
     try{
        await fetch(`/api/stream_event/${streamIdLeader}`, {
          method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
        });
     }catch(err){console.warn('stream_event failed', err);}
  }

  function startTick(){
     if(tickTimer||!streamIdLeader) return;
     tickTimer = setInterval(()=>{
        if(!streamIdLeader) return;
        sendStreamEvent({action:'tick', idx: currentIndex, position: media.currentTime, paused: media.paused});
     },1500);
  }
  function stopTick(){ if(tickTimer){clearInterval(tickTimer);tickTimer=null;} }

  streamBtn.onclick = async ()=>{
     if(streamIdLeader){
        alert('Stream already running. Share this URL:\n'+window.location.origin+'/stream/'+streamIdLeader);
        return;
     }
     const title = prompt('Stream title:', document.title);
     if(title===null) return;
     try{
        const body = {
           title,
           queue,
           idx: currentIndex,
           paused: media.paused,
           position: media.currentTime
        };
        const res = await fetch('/api/create_stream', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
        const data = await res.json();
        streamIdLeader = data.id;
        streamBtn.textContent = 'Streaming…';
        streamBtn.disabled = true;
        if(!media.paused){
           sendStreamEvent({action:'play', position: media.currentTime, paused:false});
           startTick();
        }
        const overlay=document.getElementById('shareOverlay');
        const linkEl=document.getElementById('shareLink');
        linkEl.href=data.url;linkEl.textContent=data.url;
        overlay.style.display='block';
        const copyBtn=document.getElementById('copyLinkBtn');
        copyBtn.onclick=()=> {
           if(!media.paused){ sendStreamEvent({action:'play'});} // notify listeners to start
           navigator.clipboard.writeText(data.url).catch(()=>{});
        };
        document.getElementById('closeShare').onclick=()=> overlay.style.display='none';
     }catch(err){alert('Stream creation failed: '+err);}  
  };

  // stop tick when window unload
  window.addEventListener('beforeunload',()=> stopTick());

  // ==============================
  // REMOTE CONTROL SYNCHRONIZATION
  // ==============================
  
  // Sync player state with remote control API
  async function syncRemoteState() {
    try {
      const currentTrack = currentIndex >= 0 && currentIndex < queue.length ? queue[currentIndex] : null;
      const playerState = {
        current_track: currentTrack,
        playing: !media.paused && currentTrack !== null,
        volume: media.volume,
        progress: media.currentTime || 0,
        playlist: queue,
        current_index: currentIndex,
        last_update: Date.now() / 1000
      };
      
      console.log('🎮 Syncing remote state:', {
        track: currentTrack?.name || 'No track',
        playing: playerState.playing,
        progress: Math.floor(playerState.progress),
        index: currentIndex
      });
      
      // Update the global PLAYER_STATE via internal API call
      const response = await fetch('/api/remote/sync_internal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(playerState)
      });
      
      if (!response.ok) {
        console.warn('Remote sync failed with status:', response.status);
      }
    } catch(err) {
      console.warn('Remote sync failed:', err);
    }
  }
  
  // Listen for remote control commands
  async function pollRemoteCommands() {
    try {
      const response = await fetch('/api/remote/commands');
      if (response.ok) {
        const commands = await response.json();
        for (const command of commands) {
          await executeRemoteCommand(command);
        }
      }
    } catch(err) {
      console.warn('Remote polling failed:', err);
    }
  }
  
  // Execute remote control commands
  async function executeRemoteCommand(command) {
    console.log('🎮 [Remote] Executing command:', command.type);
    
    try {
      switch(command.type) {
        case 'play':
          console.log('🎮 [Remote] Toggle play/pause');
          if (media.paused) {
            await media.play();
          } else {
            media.pause();
          }
          break;
          
        case 'next':
          console.log('🎮 [Remote] Next track');
          nextBtn.click();
          break;
          
        case 'prev':
          console.log('🎮 [Remote] Previous track');
          prevBtn.click();
          break;
          
        case 'stop':
          console.log('🎮 [Remote] Stop playback');
          media.pause();
          media.currentTime = 0;
          break;
          
        case 'volume':
          if (command.volume !== undefined) {
            console.log('🎮 [Remote] Set volume:', Math.round(command.volume * 100) + '%');
            media.volume = command.volume;
            cVol.value = command.volume;
            updateMuteIcon();
            // Note: Volume is already saved by the remote API endpoint
          }
          break;
          
        case 'shuffle':
          console.log('🎮 [Remote] Shuffle playlist');
          shuffleBtn.click();
          break;
          
        case 'like':
          console.log('🎮 [Remote] Like track');
          cLike.click();
          break;
          
        case 'youtube':
          console.log('🎮 [Remote] Open YouTube');
          cYoutube.click();
          break;
          
        case 'fullscreen':
          console.log('🎮 [Remote] Toggle fullscreen');
          cFull.click();
          break;
          
        default:
          console.warn('🎮 [Remote] Unknown command:', command.type);
      }
      
      // Sync state after command execution
      setTimeout(syncRemoteState, 200);
    } catch (error) {
      console.error('🎮 [Remote] Error executing command:', error);
    }
  }
  
  // Enhanced event listeners for remote sync
  media.addEventListener('play', syncRemoteState);
  media.addEventListener('pause', syncRemoteState);
  media.addEventListener('loadeddata', syncRemoteState);
  media.addEventListener('timeupdate', () => {
    // Sync every 2 seconds during playback
    if (!media.paused && Math.floor(media.currentTime) % 2 === 0) {
      syncRemoteState();
    }
  });
  
  // Override existing functions to include remote sync
  const originalPlayIndex = playIndex;
  window.playIndex = function(idx) {
    originalPlayIndex.call(this, idx);
    setTimeout(syncRemoteState, 200);
  };
  
  const originalTogglePlay = togglePlay;
  window.togglePlay = function() {
    originalTogglePlay.call(this);
    setTimeout(syncRemoteState, 200);
  };
  
  // Initial state sync after everything is loaded
  setTimeout(() => {
    if (currentIndex >= 0) {
      syncRemoteState();
    }
    // Start periodic sync every 3 seconds
    setInterval(syncRemoteState, 3000);
  }, 1000);
  
  // Periodic remote command polling (every 1 second)
  setInterval(pollRemoteCommands, 1000);
  
  console.log('🎮 Remote control synchronization initialized');
})(); 