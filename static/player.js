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
    media.src = track.url;
    media.play();
    renderList();
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

  renderList();
})(); 