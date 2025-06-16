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
  const stopBtn = document.getElementById('stopBtn');
  const nextBtn = document.getElementById('nextBtn');
  const prevBtn = document.getElementById('prevBtn');
  const playBtn = document.getElementById('playBtn');
  const fullBtn = document.getElementById('fullBtn');
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

  const playlistRel = typeof PLAYLIST_REL !== 'undefined' ? PLAYLIST_REL : '';
  let tracks = await fetchTracks(playlistRel);
  let queue = [...tracks];
  let currentIndex = -1;

  // ---- Google Cast Integration ----
  let castContext = null;
  let pendingCastTrack=null;

  window.__onGCastApiAvailable = function(isAvailable){
      console.log('Cast API callback, isAvailable=', isAvailable);
      if(isAvailable){
          castContext = cast.framework.CastContext.getInstance();
          castContext.setOptions({
              receiverApplicationId: chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
              autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED
          });
          // ensure launcher visible
          const castBtn = document.getElementById('castBtn');
          if(castBtn){
              castBtn.style.display='inline-flex';
              console.log('Cast button forced visible');
          }else{
              console.warn('Cast button element not found');
          }
      }
  };

  function castLoad(track){
      if(!castContext) return;
      const session = castContext.getCurrentSession();
      if(!session){
          pendingCastTrack=track;
          return;
      }
      let absUrl = new URL(track.url, window.location.href).href;
      // if hostname is localhost, replace with current local IP (taken from location)
      if (absUrl.includes('localhost')) {
          if (typeof SERVER_IP !== 'undefined' && SERVER_IP) {
              absUrl = absUrl.replace('localhost', SERVER_IP);
          } else {
              absUrl = absUrl.replace('localhost', window.location.hostname);
          }
      }
      const ext = absUrl.split('.').pop().toLowerCase();
      const mimeMap = {mp4:'video/mp4', webm:'video/webm', mkv:'video/x-matroska', mov:'video/quicktime', mp3:'audio/mpeg', m4a:'audio/mp4', opus:'audio/ogg', flac:'audio/flac'};
      const mime = mimeMap[ext] || 'video/mp4';
      const mediaInfo = new chrome.cast.media.MediaInfo(absUrl, mime);
      mediaInfo.metadata = new chrome.cast.media.GenericMediaMetadata();
      mediaInfo.metadata.title = track.name;
      const request = new chrome.cast.media.LoadRequest(mediaInfo);
      session.loadMedia(request).catch(console.error);
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

    // report play start once per track
    reportEvent(track.video_id, 'start');
  }

  function playIndex(idx){
    loadTrack(idx,true);
  }

  media.addEventListener('ended', () => {
    if (currentIndex + 1 < queue.length) {
      playIndex(currentIndex + 1);
    }
    // report play finish for previous track
    if(currentIndex >=0 && currentIndex < queue.length){
        const track = queue[currentIndex];
        reportEvent(track.video_id, 'finish');
    }
  });

  shuffleBtn.onclick = () => {
    queue = [...tracks];
    shuffle(queue);
    playIndex(0);
  };

  stopBtn.onclick = () => {
    media.pause();
    media.currentTime = 0;
  };

  nextBtn.onclick = () => {
    if (currentIndex + 1 < queue.length) {
      playIndex(currentIndex + 1);
    }
  };

  prevBtn.onclick = () => {
    if (currentIndex - 1 >= 0) {
      playIndex(currentIndex - 1);
    }
  };

  playBtn.onclick = () => {
    if (media.paused) {
      media.play();
    } else {
      media.pause();
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
    cPlay.textContent = '⏸';
  });
  media.addEventListener('pause', () => {
    cPlay.textContent = '▶️';
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
    cMute.textContent = media.muted ? '🔈' : '🔊';
  };
  cVol.oninput = () => {
    media.volume = parseFloat(cVol.value);
    media.muted = media.volume === 0;
    cMute.textContent = media.muted ? '🔈' : '🔊';
  };
  // sync initial volume icon
  media.volume = 1;

  // auto-shuffle and start playback on first load
  if (queue.length > 0) {
      shuffle(queue);
      playIndex(0); // starts playing first track of shuffled queue
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

  function updateFsVisibility(){
     if(document.fullscreenElement){
        listElem.style.display='none';
     }else{
        listElem.style.display='';
     }
  }
  document.addEventListener('fullscreenchange',updateFsVisibility);
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

  async function reportEvent(videoId, event){
     if(!videoId) return;
     try{
        await fetch('/api/event', {
           method:'POST',
           headers:{'Content-Type':'application/json'},
           body: JSON.stringify({video_id: videoId, event})
        });
     }catch(err){
        console.warn('event report failed', err);
     }
  }
})(); 