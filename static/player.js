async function fetchTracks() {
  const res = await fetch('/api/tracks');
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

  let tracks = await fetchTracks();
  let queue = [...tracks];
  let currentIndex = -1;

  function renderList() {
    listElem.innerHTML = '';
    queue.forEach((t, idx) => {
      const li = document.createElement('li');
      li.textContent = t.name;
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
    renderList();
  }

  function playIndex(idx){
    loadTrack(idx,true);
  }

  media.addEventListener('ended', () => {
    if (currentIndex + 1 < queue.length) {
      playIndex(currentIndex + 1);
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

  // auto-load first track
  if(queue.length>0){
      loadTrack(0,false);
  }else{
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
})(); 