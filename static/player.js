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
  const audio = document.getElementById('audio');
  const listElem = document.getElementById('tracklist');
  const shuffleBtn = document.getElementById('shuffleBtn');
  const stopBtn = document.getElementById('stopBtn');

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

  function playIndex(idx) {
    if (idx < 0 || idx >= queue.length) return;
    currentIndex = idx;
    const track = queue[currentIndex];
    audio.src = track.url;
    audio.play();
    renderList();
  }

  audio.addEventListener('ended', () => {
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
    audio.pause();
    audio.currentTime = 0;
  };

  renderList();
})(); 