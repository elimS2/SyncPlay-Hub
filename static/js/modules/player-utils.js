/**
 * Общие утилиты для плееров
 * Централизованное управление дублирующимися методами
 */

// ===== УТИЛИТЫ МАССИВОВ =====

/**
 * Перемешивает массив случайным образом (алгоритм Фишера-Йетса)
 * @param {Array} array - массив для перемешивания
 */
export function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
}

/**
 * Умное перемешивание на основе даты последнего воспроизведения
 * Группирует треки по времени последнего воспроизведения: 
 * никогда не играли > год назад > месяц назад > неделя назад > день назад > сегодня
 * @param {Array} list - список треков для перемешивания
 * @returns {Array} - перемешанный список треков
 */
export function smartShuffle(list){
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

// ===== АНАЛИЗ КАНАЛОВ =====

/**
 * Определяет тип канала/группы по пути файла
 * @param {Object} track - объект трека с полем relpath
 * @returns {Object} - объект с типом канала, группой и флагом isChannel
 */
export function detectChannelGroup(track) {
  /**
   * Detect channel group from file path
   * Returns: { type: 'music'|'news'|'education'|'podcasts'|'playlist', group: string, isChannel: boolean }
   */
  if (!track || !track.relpath) {
    return { type: 'playlist', group: 'Unknown', isChannel: false };
  }
  
  const path = track.relpath.toLowerCase();
  
  // Check for channel group patterns: Music/Channel-Artist/, News/Channel-News/, etc.
  const channelGroupMatch = path.match(/^(music|news|education|podcasts)\/channel-([^\/]+)\//);
  if (channelGroupMatch) {
    const groupType = channelGroupMatch[1];
    const channelName = channelGroupMatch[2];
    return { 
      type: groupType, 
      group: `${groupType.charAt(0).toUpperCase() + groupType.slice(1)} Channels`,
      channel: channelName,
      isChannel: true 
    };
  }
  
  // Check for direct channel folders: Channel-Artist/
  const directChannelMatch = path.match(/^channel-([^\/]+)\//);
  if (directChannelMatch) {
    const channelName = directChannelMatch[1];
    return { 
      type: 'music', // Default to music for direct channels
      group: 'Channels',
      channel: channelName,
      isChannel: true 
    };
  }
  
  // Regular playlist
  const playlistMatch = path.match(/^([^\/]+)\//);
  if (playlistMatch) {
    const playlistName = playlistMatch[1];
    return { 
      type: 'playlist', 
      group: playlistName,
      isChannel: false 
    };
  }
  
  return { type: 'playlist', group: 'Unknown', isChannel: false };
}

/**
 * Умное перемешивание на основе типа канала
 * - Music: Случайное перемешивание
 * - News: Хронологический порядок (новые первыми)
 * - Education: Последовательный порядок (старые первыми)
 * - Podcasts: Последовательный порядок (новые первыми)
 * - Playlists: Умное перемешивание (существующая логика)
 * @param {Array} tracks - массив треков для обработки
 * @returns {Array} - обработанный массив треков
 */
export function smartChannelShuffle(tracks) {
  /**
   * Smart shuffle based on channel groups:
   * - Music: Random shuffle with repeat
   * - News: Chronological newest-first (by filename/date)
   * - Education: Sequential oldest-first
   * - Podcasts: Sequential newest-first
   * - Playlists: Smart shuffle (existing logic)
   */
  
  if (!tracks || tracks.length === 0) return [];
  
  // Group tracks by channel group
  const groups = {};
  tracks.forEach(track => {
    const detection = detectChannelGroup(track);
    const key = `${detection.type}:${detection.group}`;
    if (!groups[key]) {
      groups[key] = { tracks: [], detection: detection };
    }
    groups[key].tracks.push(track);
  });
  
  // Process each group according to its type
  const processedTracks = [];
  
  Object.values(groups).forEach(group => {
    const { tracks: groupTracks, detection } = group;
    let orderedTracks = [...groupTracks];
    
    switch (detection.type) {
      case 'music':
        // Random shuffle for music
        shuffle(orderedTracks);
        console.log(`🎵 Music group "${detection.group}": ${orderedTracks.length} tracks shuffled randomly`);
        break;
        
      case 'news':
        // Chronological newest-first for news
        orderedTracks.sort((a, b) => {
          // Try to extract date from filename or use last_play as fallback
          const aTime = a.last_play || a.name;
          const bTime = b.last_play || b.name;
          return bTime.localeCompare(aTime); // Newest first
        });
        console.log(`📰 News group "${detection.group}": ${orderedTracks.length} tracks ordered newest-first`);
        break;
        
      case 'education':
        // Sequential oldest-first for education
        orderedTracks.sort((a, b) => {
          const aTime = a.last_play || a.name;
          const bTime = b.last_play || b.name;
          return aTime.localeCompare(bTime); // Oldest first
        });
        console.log(`🎓 Education group "${detection.group}": ${orderedTracks.length} tracks ordered oldest-first`);
        break;
        
      case 'podcasts':
        // Sequential newest-first for podcasts
        orderedTracks.sort((a, b) => {
          const aTime = a.last_play || a.name;
          const bTime = b.last_play || b.name;
          return bTime.localeCompare(aTime); // Newest first
        });
        console.log(`🎙️ Podcast group "${detection.group}": ${orderedTracks.length} tracks ordered newest-first`);
        break;
        
      case 'playlist':
      default:
        // Use existing smart shuffle logic for playlists
        orderedTracks = smartShuffle(groupTracks);
        console.log(`📋 Playlist "${detection.group}": ${orderedTracks.length} tracks smart shuffled`);
        break;
    }
    
    processedTracks.push(...orderedTracks);
  });
  
  return processedTracks;
}

/**
 * Получает информацию о воспроизведении для текущего микса треков
 * Анализирует треки и возвращает статистику по группам каналов
 * @param {Array} tracks - массив треков для анализа
 * @returns {Array|null} - массив с информацией о группах или null если треков нет
 */
export function getGroupPlaybackInfo(tracks) {
  /**
   * Get playback information for current track mix
   */
  if (!tracks || tracks.length === 0) return null;
  
  const groups = {};
  tracks.forEach(track => {
    const detection = detectChannelGroup(track);
    const key = `${detection.type}:${detection.group}`;
    if (!groups[key]) {
      groups[key] = { count: 0, detection: detection };
    }
    groups[key].count++;
  });
  
  const groupInfo = Object.values(groups).map(group => ({
    type: group.detection.type,
    group: group.detection.group,
    count: group.count,
    isChannel: group.detection.isChannel
  }));
  
  return groupInfo;
}

// ===== СОРТИРОВКА ТРЕКОВ =====

/**
 * Sort tracks by YouTube publish date in ascending order (oldest first)
 * Supports different field naming schemas for regular playlists vs virtual playlists
 * @param {Array} tracks - Array of track objects to sort
 * @param {string} schema - Field naming schema: 'regular' (youtube_*) or 'virtual' (no prefix)
 * @returns {Array} Sorted array of tracks (oldest first)
 */
export function orderByPublishDate(tracks, schema = 'regular') {
  if (!tracks || tracks.length === 0) return [];

  const orderedTracks = [...tracks];
  
  // Define field names based on schema
  const fields = schema === 'virtual' ? {
    timestamp: 'timestamp',
    releaseTimestamp: 'release_timestamp', 
    releaseYear: 'release_year'
  } : {
    timestamp: 'youtube_timestamp',
    releaseTimestamp: 'youtube_release_timestamp',
    releaseYear: 'youtube_release_year'
  };
  
  orderedTracks.sort((a, b) => {
    // Get publish dates for comparison
    const getPublishTimestamp = (track) => {
      // Priority: timestamp > release_timestamp > release_year > fallback to 0
      if (track[fields.timestamp] && track[fields.timestamp] > 0) {
        return track[fields.timestamp];
      }
      if (track[fields.releaseTimestamp] && track[fields.releaseTimestamp] > 0) {
        return track[fields.releaseTimestamp];
      }
      if (track[fields.releaseYear] && track[fields.releaseYear] > 0) {
        // Convert year to approximate timestamp (January 1st of that year)
        return new Date(`${track[fields.releaseYear]}-01-01`).getTime() / 1000;
      }
      // Fallback for tracks without date info - put them at the beginning
      return 0;
    };

    const aTime = getPublishTimestamp(a);
    const bTime = getPublishTimestamp(b);
    
    // Sort ascending (oldest first)
    return aTime - bTime;
  });

  const schemaLabel = schema === 'virtual' ? '[Virtual]' : '';
  console.log(`📅 ${schemaLabel} Tracks ordered by publish date (oldest first): ${orderedTracks.length} tracks`);
  
  // Debug log first few tracks to verify sorting (only for virtual schema)
  if (schema === 'virtual' && orderedTracks.length > 0) {
    console.log('📅 [Virtual] First few tracks by date:');
    orderedTracks.slice(0, 3).forEach((track, idx) => {
      const date = track[fields.timestamp] ? new Date(track[fields.timestamp] * 1000).toLocaleDateString() :
                 track[fields.releaseTimestamp] ? new Date(track[fields.releaseTimestamp] * 1000).toLocaleDateString() :
                 track[fields.releaseYear] ? track[fields.releaseYear] : 'Unknown';
      console.log(`  ${idx + 1}. ${track.name} (${date})`);
    });
  }

  return orderedTracks;
}

// ===== ВСПОМОГАТЕЛЬНЫЕ УТИЛИТЫ =====

/**
 * Форматирует время в секундах в формат MM:SS
 * @param {number} s - время в секундах
 * @returns {string} - отформатированное время
 */
export function formatTime(s) {
  if (!isFinite(s)) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60).toString().padStart(2, '0');
  return `${m}:${sec}`;
}

/**
 * Обновляет отображение скорости воспроизведения
 * @param {number} currentSpeedIndex - индекс текущей скорости
 * @param {Array} speedOptions - массив доступных скоростей
 * @param {HTMLElement} speedLabel - элемент для отображения скорости
 * @param {HTMLElement} cSpeed - кнопка управления скоростью
 */
export function updateSpeedDisplay(currentSpeedIndex, speedOptions, speedLabel, cSpeed) {
  const speed = speedOptions[currentSpeedIndex];
  if (speedLabel) {
    speedLabel.textContent = `${speed}x`;
  }
  if (cSpeed) {
    cSpeed.title = `Playback Speed: ${speed}x (click to change)`;
  }
}

/**
 * Показывает уведомление пользователю
 * @param {string} message - текст уведомления
 * @param {string} type - тип уведомления ('info', 'success', 'error')
 */
export function showNotification(message, type = 'info') {
  // Create notification element
  const notification = document.createElement('div');
  notification.className = `notification notification-${type}`;
  notification.textContent = message;
  notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 12px 20px;
    border-radius: 6px;
    color: white;
    font-weight: 500;
    z-index: 10000;
    max-width: 400px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    transition: opacity 0.3s ease, transform 0.3s ease;
    transform: translateX(100%);
  `;
  
  // Set background color based on type
  if (type === 'success') {
    notification.style.backgroundColor = '#4caf50';
  } else if (type === 'error') {
    notification.style.backgroundColor = '#f44336';
  } else {
    notification.style.backgroundColor = '#2196f3';
  }
  
  // Add to document
  document.body.appendChild(notification);
  
  // Animate in
  setTimeout(() => {
    notification.style.transform = 'translateX(0)';
  }, 100);
  
  // Auto remove after 5 seconds
  setTimeout(() => {
    notification.style.opacity = '0';
    notification.style.transform = 'translateX(100%)';
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, 300);
  }, 5000);
}

/**
 * Обрабатывает колесико мыши для управления громкостью
 * @param {Event} e - событие колесика мыши
 * @param {HTMLElement} cVol - элемент управления громкостью
 * @param {HTMLMediaElement} media - медиа элемент
 * @param {Function} updateMuteIcon - функция обновления иконки mute
 * @param {Function} saveVolumeToDatabase - функция сохранения громкости в БД
 * @param {Object} volumeState - объект состояния громкости
 */
export function handleVolumeWheel(e, cVol, media, updateMuteIcon, saveVolumeToDatabase, volumeState) {
  e.preventDefault(); // Prevent page scroll
  e.stopPropagation(); // Stop event bubbling
  
  // Block remote volume commands while user is using wheel
  volumeState.isVolumeWheelActive = true;
  clearTimeout(volumeState.volumeWheelTimeout);
  volumeState.volumeWheelTimeout = setTimeout(() => {
    volumeState.isVolumeWheelActive = false;
  }, 2000); // 2 second cooldown
  
  const currentVolume = parseFloat(cVol.value);
  const step = 0.01; // 1% step
  
  let newVolume;
  if (e.deltaY < 0) {
    // Wheel up - increase volume
    newVolume = Math.min(1.0, currentVolume + step);
  } else {
    // Wheel down - decrease volume
    newVolume = Math.max(0.0, currentVolume - step);
  }
  
  // Check if we have an actual change
  if (Math.abs(newVolume - currentVolume) < 0.001) {
    return;
  }
  
  // Update slider and media volume
  cVol.value = newVolume;
  media.volume = newVolume;
  media.muted = media.volume === 0;
  updateMuteIcon();
  
  // Force visual update
  cVol.dispatchEvent(new Event('input', { bubbles: true }));
  
  saveVolumeToDatabase(media.volume);
  
  console.log(`🎚️ Volume wheel control: ${Math.round(currentVolume * 100)}% → ${Math.round(newVolume * 100)}%`);
}

// ===== УПРАВЛЕНИЕ ВОСПРОИЗВЕДЕНИЕМ =====

/**
 * Останавливает таймер синхронизации потока
 * @param {number|null} tickTimer - ID таймера для остановки
 * @returns {null} - возвращает null для обновления tickTimer
 */
export function stopTick(tickTimer) {
  if (tickTimer) {
    clearInterval(tickTimer);
    return null;
  }
  return tickTimer;
}

/**
 * Останавливает воспроизведение и сбрасывает позицию
 * @param {HTMLAudioElement} media - аудио элемент
 */
export function stopPlayback(media) {
  media.pause();
  media.currentTime = 0;
}

/**
 * Начинает воспроизведение трека по индексу
 * @param {number} idx - индекс трека для воспроизведения
 * @param {Function} loadTrack - функция загрузки трека
 */
export function playIndex(idx, loadTrack) {
  loadTrack(idx, true);
}

/**
 * Обновляет иконку звука в зависимости от состояния медиа
 * @param {HTMLAudioElement} media - аудио элемент
 * @param {HTMLElement} cMute - элемент кнопки звука
 */
export function updateMuteIcon(media, cMute) {
  if (media.muted || media.volume === 0) {
    cMute.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg>';
  } else {
    cMute.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/></svg>';
  }
}

// ===== НАВИГАЦИЯ ПО ТРЕКАМ =====

/**
 * Переход к следующему треку в очереди
 * @param {number} currentIndex - текущий индекс трека
 * @param {Array} queue - очередь треков
 * @param {Function} reportEvent - функция отправки события
 * @param {Function} playIndex - функция воспроизведения по индексу
 * @param {Function} sendStreamEvent - функция отправки потокового события
 * @param {HTMLAudioElement} media - аудио элемент
 */
export function nextTrack(currentIndex, queue, reportEvent, playIndex, sendStreamEvent, media) {
  if (currentIndex + 1 < queue.length) {
    // send event for current track before switching
    if(currentIndex>=0){ reportEvent(queue[currentIndex].video_id,'next'); }
    playIndex(currentIndex + 1);
    sendStreamEvent({action:'next', idx: currentIndex, paused: media.paused, position:0});
  }
}

/**
 * Переход к предыдущему треку в очереди
 * @param {number} currentIndex - текущий индекс трека
 * @param {Array} queue - очередь треков
 * @param {Function} reportEvent - функция отправки события
 * @param {Function} playIndex - функция воспроизведения по индексу
 * @param {Function} sendStreamEvent - функция отправки потокового события
 * @param {HTMLAudioElement} media - аудио элемент
 */
export function prevTrack(currentIndex, queue, reportEvent, playIndex, sendStreamEvent, media) {
  if (currentIndex - 1 >= 0) {
    if(currentIndex>=0){ reportEvent(queue[currentIndex].video_id,'prev'); }
    playIndex(currentIndex - 1);
    sendStreamEvent({action:'prev', idx: currentIndex, paused: media.paused, position: media.currentTime});
  }
}

// ===== ПОТОКОВЫЕ СОБЫТИЯ =====

/**
 * Отправляет событие потокового вещания
 * @param {Object} payload - данные события для отправки
 * @param {string|null} streamIdLeader - ID лидера потока
 */
export async function sendStreamEvent(payload, streamIdLeader) {
  if(!streamIdLeader) return;
  try{
     await fetch(`/api/stream_event/${streamIdLeader}`, {
       method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
     });
  }catch(err){console.warn('stream_event failed', err);}
}

/**
 * Запускает таймер синхронизации потока
 * @param {number|null} tickTimer - текущий ID таймера
 * @param {string|null} streamIdLeader - ID лидера потока
 * @param {Function} sendStreamEventFn - функция отправки событий потока
 * @param {number} currentIndex - текущий индекс трека
 * @param {HTMLAudioElement} media - аудио элемент
 * @returns {number|null} - ID нового таймера или null
 */
export function startTick(tickTimer, streamIdLeader, sendStreamEventFn, currentIndex, media) {
  if(tickTimer||!streamIdLeader) return tickTimer;
  
  const newTickTimer = setInterval(()=>{
     if(!streamIdLeader) return;
     sendStreamEventFn({action:'tick', idx: currentIndex, position: media.currentTime, paused: media.paused});
  },1500);
  
  return newTickTimer;
}

// ===== ОБРАБОТКА СОБЫТИЙ =====

/**
 * Отправляет событие аналитики на сервер
 * @param {string} videoId - ID видео
 * @param {string} event - тип события
 * @param {number|null} position - позиция воспроизведения (по умолчанию null)
 */
export async function reportEvent(videoId, event, position = null) {
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

/**
 * Проверяет возможность автоудаления завершенного трека из канала
 * @param {Object} track - объект трека
 * @param {Function} detectChannelGroupFn - функция определения группы канала
 * @param {HTMLAudioElement} media - аудио элемент
 */
export async function triggerAutoDeleteCheck(track, detectChannelGroupFn, media) {
  /**
   * Trigger auto-delete check for finished track if it's from a channel.
   */
  try {
    if (!track || !track.video_id) return;
    
    // Detect if this is channel content
    const detection = detectChannelGroupFn(track);
    if (!detection.isChannel) {
      console.log(`🚫 Auto-delete skip: ${track.video_id} is not from a channel`);
      return;
    }
    
    const finishPosition = media.currentTime || media.duration || 0;
    
    console.log(`🗑️ Auto-delete check triggered for ${track.video_id} from ${detection.group} (${finishPosition.toFixed(1)}s)`);
    
    // The auto-delete service will handle the actual deletion logic
    // This just logs that the finish event occurred for a channel track
    
  } catch (err) {
    console.warn('triggerAutoDeleteCheck error:', err);
   }
}

// ===== УПРАВЛЕНИЕ НАСТРОЙКАМИ =====

/**
 * Отправляет событие навигации на сервер для аналитики
 * @param {string} video_id - ID видео
 * @param {number} seek_from - начальная позиция навигации в секундах
 * @param {number} seek_to - конечная позиция навигации в секундах
 * @param {string} source - источник навигации (progress_bar, keyboard, etc.)
 */
export async function recordSeekEvent(video_id, seek_from, seek_to, source) {
  try {
    const payload = {
      video_id: video_id,
      seek_from: seek_from,
      seek_to: seek_to,
      source: source
    };
    
    const response = await fetch('/api/seek', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (response.ok) {
      const data = await response.json();
      const direction = data.direction;
      const distance = Math.round(data.distance);
      console.log(`⏩ Seek ${direction}: ${Math.round(seek_from)}s → ${Math.round(seek_to)}s (${distance}s) via ${source}`);
    }
  } catch (error) {
    console.warn('⚠️ Failed to record seek event:', error);
  }
}

// ===== REMOTE CONTROL И СИНХРОНИЗАЦИЯ =====

/**
 * Выполняет клавиатурный поиск в медиа-элементе
 * @param {number} offsetSeconds - смещение в секундах (может быть отрицательным)
 * @param {Object} context - контекст с необходимыми переменными
 * @param {number} context.currentIndex - текущий индекс трека
 * @param {Array} context.queue - очередь треков
 * @param {HTMLMediaElement} context.media - медиа-элемент
 * @param {Function} context.recordSeekEvent - функция записи события поиска
 */
export function performKeyboardSeek(offsetSeconds, context) {
  const { currentIndex, queue, media, recordSeekEvent } = context;
  
  if (currentIndex < 0 || currentIndex >= queue.length || !media.duration) return;
  
  const seekFrom = media.currentTime;
  const seekTo = Math.max(0, Math.min(media.duration, seekFrom + offsetSeconds));
  
  if (Math.abs(seekTo - seekFrom) >= 1.0) {
    media.currentTime = seekTo;
    const track = queue[currentIndex];
    recordSeekEvent(track.video_id, seekFrom, seekTo, 'keyboard');
  }
}

/**
 * Синхронизирует состояние кнопок лайков с remote state
 */
export async function syncLikeButtonsWithRemote() {
  try {
    const response = await fetch('/api/remote/status');
    if (response.ok) {
      const status = await response.json();
      
      const likeButton = document.getElementById('cLike');
      const dislikeButton = document.getElementById('cDislike');
      
      if (likeButton && status.like_active !== undefined) {
        if (status.like_active) {
          likeButton.classList.add('like-active');
        } else {
          likeButton.classList.remove('like-active');
        }
      }
      
      if (dislikeButton && status.dislike_active !== undefined) {
        if (status.dislike_active) {
          dislikeButton.classList.add('dislike-active');
        } else {
          dislikeButton.classList.remove('dislike-active');
        }
      }
    }
  } catch (error) {
    console.warn('Failed to sync like buttons with remote:', error);
  }
}

/**
 * Синхронизирует лайки после действий пользователя
 * @param {string} video_id - ID видео
 * @param {string} action - действие ('like' или 'dislike')
 * @param {Function} syncRemoteState - функция синхронизации remote state
 */
export async function syncLikesAfterAction(video_id, action, syncRemoteState) {
  console.log(`🎵 [Like Sync] Syncing likes after ${action} for ${video_id}`);
  
  // Just sync remote state to update remote control
  setTimeout(async () => {
    await syncRemoteState();
  }, 200);
}

/**
 * Настраивает обработчики синхронизации лайков для кнопок
 * @param {Object} context - контекст с необходимыми данными
 * @param {number} context.currentIndex - текущий индекс трека
 * @param {Array} context.queue - очередь треков
 * @param {Function} context.syncLikesAfterAction - функция синхронизации лайков
 */
export function setupLikeSyncHandlers(context) {
  const { currentIndex, queue, syncLikesAfterAction } = context;
  
  const likeButton = document.getElementById('cLike');
  const dislikeButton = document.getElementById('cDislike');
  
  if (likeButton) {
    // Store original handler
    const originalLikeHandler = likeButton.onclick;
    
    likeButton.onclick = async function(e) {
      // Call original handler
      if (originalLikeHandler) {
        originalLikeHandler.call(this, e);
      }
      
      // Sync likes after action
      const currentTrack = currentIndex >= 0 && currentIndex < queue.length ? queue[currentIndex] : null;
      if (currentTrack && currentTrack.video_id) {
        await syncLikesAfterAction(currentTrack.video_id, 'like');
      }
    };
  }
  
  if (dislikeButton) {
    // Store original handler
    const originalDislikeHandler = dislikeButton.onclick;
    
    dislikeButton.onclick = async function(e) {
      // Call original handler
      if (originalDislikeHandler) {
        originalDislikeHandler.call(this, e);
      }
      
      // Sync likes after action
      const currentTrack = currentIndex >= 0 && currentIndex < queue.length ? queue[currentIndex] : null;
      if (currentTrack && currentTrack.video_id) {
        await syncLikesAfterAction(currentTrack.video_id, 'dislike');
      }
    };
  }
}

/**
 * Сохраняет громкость в базу данных с дебаунсингом
 * @param {number} volume - уровень громкости (0.0-1.0)
 * @param {Object} context - контекст для получения данных о треке
 * @param {number} context.currentIndex - текущий индекс трека
 * @param {Array} context.queue - очередь треков
 * @param {HTMLAudioElement} context.media - аудио элемент
 * @param {Object} context.state - объект состояния с volumeSaveTimeout и lastSavedVolume
 */
export async function saveVolumeToDatabase(volume, context) {
  clearTimeout(context.state.volumeSaveTimeout);
  context.state.volumeSaveTimeout = setTimeout(async () => {
    try {
      const currentTrack = context.currentIndex >= 0 && context.currentIndex < context.queue.length ? context.queue[context.currentIndex] : null;
      const payload = {
        volume: volume,
        volume_from: context.state.lastSavedVolume || 1.0,
        video_id: currentTrack ? currentTrack.video_id : 'system',
        position: context.media.currentTime || null,
        source: 'web'
      };
      
      await fetch('/api/volume/set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      console.log(`💾 Volume saved: ${Math.round((context.state.lastSavedVolume || 1.0) * 100)}% → ${Math.round(volume * 100)}%`);
      if (currentTrack) {
        console.log(`🎵 Track: ${currentTrack.name} at ${Math.round(context.media.currentTime)}s`);
      }
      
      context.state.lastSavedVolume = volume;
    } catch (error) {
      console.warn('⚠️ Failed to save volume:', error);
    }
  }, 500); // Debounce by 500ms to avoid excessive API calls
}

/**
 * Загружает сохраненную громкость из базы данных
 * @param {HTMLAudioElement} media - аудио элемент
 * @param {HTMLElement} cVol - элемент управления громкостью
 * @param {Object} state - объект состояния с lastSavedVolume
 * @param {Function} updateMuteIcon - функция обновления иконки звука
 */
export async function loadSavedVolume(media, cVol, state, updateMuteIcon) {
  try {
    const response = await fetch('/api/volume/get');
    const data = await response.json();
    
    if (data.volume !== undefined) {
      media.volume = data.volume;
      cVol.value = data.volume;
      state.lastSavedVolume = data.volume; // Set initial saved volume
      console.log(`🔊 Loaded saved volume: ${data.volume_percent}%`);
    } else {
      // Default volume if no saved setting
      media.volume = 1.0;
      cVol.value = 1.0;
      state.lastSavedVolume = 1.0; // Set default as saved volume
      console.log('🔊 Using default volume: 100%');
    }
  } catch (error) {
    console.warn('⚠️ Failed to load saved volume, using default:', error);
    media.volume = 1.0;
    cVol.value = 1.0;
    state.lastSavedVolume = 1.0; // Set default as saved volume
  }
  
  updateMuteIcon();
}

// ==============================
// КОНТРОЛЬ ВОСПРОИЗВЕДЕНИЯ
// ==============================

/**
 * Переключает воспроизведение (пауза/воспроизведение)
 * Автоматически синхронизируется с потоковым API и запускает тикер
 * @param {Object} context - контекст с media, sendStreamEvent, startTick
 */
export function togglePlayback(context) {
    const { media, sendStreamEvent, startTick } = context || window;
    
    if (media.paused) {
        media.play();
        sendStreamEvent({action:'play', position: media.currentTime, paused:false});
        startTick();
    } else {
        media.pause();
        sendStreamEvent({action:'pause', position: media.currentTime, paused:true});
    }
}

// ==============================
// ПОЛНОЭКРАННЫЙ РЕЖИМ
// ==============================

/**
 * Показывает контролы в полноэкранном режиме с автоскрытием через 3 секунды
 * Использует глобальные переменные: customControls, controlBar, fsTimer
 * @param {Object} context - контекст с customControls, controlBar, fsTimer
 */
export function showFsControls(context) {
    const { customControls, controlBar, fsTimer } = context || window;
    
    if(!document.fullscreenElement) return;
    customControls.classList.remove('hidden');
    controlBar.classList.remove('hidden');
    clearTimeout(fsTimer);
    
    // Обновляем fsTimer в контексте или глобально
    const newTimer = setTimeout(()=>{
        if(document.fullscreenElement){
            customControls.classList.add('hidden');
            controlBar.classList.add('hidden');
        }
    },3000);
    
    if (context) {
        context.fsTimer = newTimer;
    } else {
        window.fsTimer = newTimer;
    }
}

/**
 * Обновляет видимость элементов при входе/выходе из полноэкранного режима
 * Управляет видимостью списка и настраивает обработчики событий мыши
 * @param {Object} context - контекст с listElem, customControls, controlBar, wrapper, fsTimer
 */
export function updateFsVisibility(context) {
    const { listElem, customControls, controlBar, wrapper, fsTimer } = context || window;
    
    if(document.fullscreenElement){
        listElem.style.display='none';
        showFsControls(context);
        // mouse move to reveal controls
        wrapper.addEventListener('mousemove', () => showFsControls(context));
    }else{
        listElem.style.display='';
        customControls.classList.remove('hidden');
        controlBar.classList.remove('hidden');
        wrapper.removeEventListener('mousemove', () => showFsControls(context));
        clearTimeout(fsTimer);
    }
}

/**
 * Синхронизирует состояние плеера с remote control API
 * @param {string} playerType - тип плеера ('regular' или 'virtual')
 * @param {Object} context - контекст с currentIndex, queue, media
 */
export async function syncRemoteState(playerType = 'regular', context) {
    const ctx = context || window;
    const { currentIndex, queue, media } = ctx;
    
    try {
        const currentTrack = currentIndex >= 0 && currentIndex < queue.length ? queue[currentIndex] : null;
        
        // Get current like/dislike button states
        const likeButton = document.getElementById('cLike');
        const dislikeButton = document.getElementById('cDislike');
        const likeActive = likeButton ? likeButton.classList.contains('like-active') : false;
        const dislikeActive = dislikeButton ? dislikeButton.classList.contains('dislike-active') : false;
        
        const playerState = {
            current_track: currentTrack,
            playing: !media.paused && currentTrack !== null,
            volume: media.volume,
            progress: media.currentTime || 0,
            playlist: queue,
            current_index: currentIndex,
            last_update: Date.now() / 1000,
            player_type: playerType,
            player_source: window.location.pathname,
            like_active: likeActive,
            dislike_active: dislikeActive
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

// ==============================
// ПОЛЬЗОВАТЕЛЬСКИЙ ИНТЕРФЕЙС
// ==============================

/**
 * Настраивает глобальную систему всплывающих подсказок для элементов трека
 * Создает единый tooltip элемент и добавляет обработчики для всех треков с data-tooltip-html
 * @param {HTMLElement} listElem - элемент списка треков для поиска tooltip элементов
 */
export function setupGlobalTooltip(listElem) {
    // Remove existing tooltip if any
    const existingTooltip = document.getElementById('global-tooltip');
    if (existingTooltip) {
        existingTooltip.remove();
    }
    
    // Create global tooltip element
    const tooltip = document.createElement('div');
    tooltip.id = 'global-tooltip';
    tooltip.className = 'custom-tooltip';
    tooltip.style.display = 'none';
    document.body.appendChild(tooltip);
    
    // Add event listeners to all tracks with tooltip data
    const trackItems = listElem.querySelectorAll('li[data-tooltip-html]');
    
    trackItems.forEach(item => {
        item.addEventListener('mouseenter', (e) => {
            const tooltipHTML = item.getAttribute('data-tooltip-html');
            tooltip.innerHTML = tooltipHTML;
            tooltip.style.display = 'block';
            
            // Position tooltip intelligently
            const rect = item.getBoundingClientRect();
            const tooltipRect = tooltip.getBoundingClientRect();
            const windowWidth = window.innerWidth;
            const windowHeight = window.innerHeight;
            
            let left, top;
            
            // Check if there's enough space on the right
            if (rect.right + tooltipRect.width + 20 <= windowWidth) {
                // Show on the right
                left = rect.right + 10;
            } else {
                // Show on the left
                left = rect.left - tooltipRect.width - 10;
            }
            
            // Ensure tooltip doesn't go off screen horizontally
            if (left < 10) left = 10;
            if (left + tooltipRect.width > windowWidth - 10) {
                left = windowWidth - tooltipRect.width - 10;
            }
            
            // Position vertically
            top = rect.top;
            
            // Ensure tooltip doesn't go off screen vertically
            if (top + tooltipRect.height > windowHeight - 10) {
                top = windowHeight - tooltipRect.height - 10;
            }
            if (top < 10) top = 10;
            
            tooltip.style.position = 'fixed';
            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
        });
        
                 item.addEventListener('mouseleave', () => {
             tooltip.style.display = 'none';
         });
     });
}

/**
 * Опрашивает API для получения команд remote control и выполняет их
 * @param {Function} executeRemoteCommand - функция выполнения команд
 * @param {boolean} verbose - включить детальное логирование (для virtual плеера)
 */
export async function pollRemoteCommands(executeRemoteCommand, verbose = false) {
    try {
        if (verbose) {
            console.log('🎮 [Virtual] Polling for remote commands...');
        }
        
        const response = await fetch('/api/remote/commands');
        
        if (verbose) {
            console.log('🎮 [Virtual] Poll response status:', response.status);
        }
        
        if (response.ok) {
            const commands = await response.json();
            
            if (verbose) {
                console.log('🎮 [Virtual] Poll response data:', commands);
                if (commands && commands.length > 0) {
                    console.log('🎮 [Virtual] Received commands:', commands);
                }
            }
            
            for (const command of commands) {
                await executeRemoteCommand(command);
            }
        } else if (verbose) {
            console.warn('🎮 [Virtual] Poll failed with status:', response.status);
        }
         } catch(err) {
         console.warn('Remote polling failed:', err);
     }
}

/**
 * Циклически переключает скорость воспроизведения
 * @param {Object} context - контекст с currentSpeedIndex, speedOptions, media, updateSpeedDisplay, reportEvent
 * @param {Function} savePlaylistSpeed - функция сохранения скорости в playlist настройки (опционально)
 * @param {string} playerType - тип плеера для логирования ('regular' или 'virtual')
 */
export async function cyclePlaybackSpeed(context, savePlaylistSpeed = null, playerType = 'regular') {
    const { currentSpeedIndex, speedOptions, media, updateSpeedDisplay, reportEvent, currentIndex, queue } = context;
    
    // Increment speed index cyclically
    const newSpeedIndex = (currentSpeedIndex + 1) % speedOptions.length;
    const newSpeed = speedOptions[newSpeedIndex];
    
    if (media) {
        media.playbackRate = newSpeed;
    }
    
    updateSpeedDisplay();
    
    const logPrefix = playerType === 'virtual' ? '⏩ [Virtual]' : '⏩';
    console.log(`${logPrefix} Playback speed changed to ${newSpeed}x`);
    
    // Save the new speed to playlist settings (if provided)
    if (savePlaylistSpeed) {
        await savePlaylistSpeed(newSpeed);
    }
    
    // Report speed change event if we have a current track
    if (currentIndex >= 0 && currentIndex < queue.length) {
        const track = queue[currentIndex];
        reportEvent(track.video_id, 'speed_change', media.currentTime, { speed: newSpeed });
    }
    
    return newSpeedIndex; // Return new index for updating caller's state
} 

// ==============================
// REMOTE CONTROL COMMANDS  
// ==============================

/**
 * Выполняет команды remote control с унифицированной надежной логикой
 * @param {Object} command - команда для выполнения
 * @param {Object} context - контекст выполнения
 * @param {string} playerType - тип плеера ('regular' или 'virtual') - только для логирования
 */
export async function executeRemoteCommand(command, context, playerType = 'regular') {
    const { 
        media, nextTrack, prevTrack, stopPlayback, togglePlayback, 
        isVolumeWheelActive, cVol, updateMuteIcon,
        syncRemoteState, syncLikeButtonsWithRemote
    } = context;
    
    const logPrefix = playerType === 'virtual' ? '🎮 [Virtual Remote]' : '🎮 [Remote]';
    console.log(`${logPrefix} Executing command:`, command.type);
    
    try {
        switch(command.type) {
            case 'play':
                console.log(`${logPrefix} Toggle play/pause using unified logic`);
                togglePlayback(); // Unified: всегда используем togglePlayback для надежности
                break;
                
            case 'next':
                console.log(`${logPrefix} Next track`);
                nextTrack();
                // Reset like buttons when track changes
                setTimeout(() => {
                    const likeBtn = document.getElementById('cLike');
                    const dislikeBtn = document.getElementById('cDislike');
                    if (likeBtn) likeBtn.classList.remove('like-active');
                    if (dislikeBtn) dislikeBtn.classList.remove('dislike-active');
                }, 100);
                break;
                
            case 'prev':
                console.log(`${logPrefix} Previous track`);
                prevTrack();
                // Reset like buttons when track changes
                setTimeout(() => {
                    const likeBtn = document.getElementById('cLike');
                    const dislikeBtn = document.getElementById('cDislike');
                    if (likeBtn) likeBtn.classList.remove('like-active');
                    if (dislikeBtn) dislikeBtn.classList.remove('dislike-active');
                }, 100);
                break;
                
            case 'stop':
                console.log(`${logPrefix} Stop playback`);
                stopPlayback();
                break;
                
            case 'volume':
                if (command.volume !== undefined) {
                    if (isVolumeWheelActive) {
                        break;
                    }
                    console.log(`${logPrefix} Set volume:`, Math.round(command.volume * 100) + '%');
                    media.volume = command.volume;
                    cVol.value = command.volume;
                    updateMuteIcon();
                    // Note: Volume is already saved by the remote API endpoint
                }
                break;
                
            case 'shuffle':
                console.log(`${logPrefix} Shuffle playlist - checking button`);
                const shuffleButton = document.getElementById('shuffleBtn');
                if (shuffleButton) {
                    console.log(`${logPrefix} shuffleBtn found, clicking...`);
                    shuffleButton.click();
                } else {
                    console.error(`${logPrefix} shuffleBtn not found!`);
                }
                break;
                
            case 'like':
                console.log(`${logPrefix} Like track - checking button`);
                const likeButton = document.getElementById('cLike');
                if (likeButton) {
                    console.log(`${logPrefix} cLike found, clicking...`);
                    likeButton.click();
                } else {
                    console.error(`${logPrefix} cLike button not found!`);
                }
                break;
                
            case 'dislike':
                console.log(`${logPrefix} Dislike track - checking button`);
                const dislikeButton = document.getElementById('cDislike');
                if (dislikeButton) {
                    console.log(`${logPrefix} cDislike found, clicking...`);
                    dislikeButton.click();
                } else {
                    console.error(`${logPrefix} cDislike button not found!`);
                }
                break;
                
            case 'youtube':
                console.log(`${logPrefix} Open YouTube - checking button`);
                const youtubeButton = document.getElementById('cYoutube');
                if (youtubeButton) {
                    console.log(`${logPrefix} cYoutube found, clicking...`);
                    youtubeButton.click();
                } else {
                    console.error(`${logPrefix} cYoutube button not found!`);
                }
                break;
                
            case 'fullscreen':
                console.log(`${logPrefix} Toggle fullscreen - checking button`);
                const fullscreenButton = document.getElementById('cFull');
                if (fullscreenButton) {
                    console.log(`${logPrefix} cFull found, clicking...`);
                    fullscreenButton.click();
                } else {
                    console.error(`${logPrefix} cFull button not found!`);
                }
                break;
                
            default:
                console.warn(`${logPrefix} Unknown command:`, command.type);
        }
        
        // Sync state after command execution
        setTimeout(syncRemoteState, 200);
        
        // Sync like buttons with remote state
        setTimeout(syncLikeButtonsWithRemote, 300);
    } catch (error) {
        console.error(`${logPrefix} Error executing command:`, error);
    }
}

// ==============================
// TRACK DELETION
// ==============================

/**
 * Удаляет трек из плейлиста с освобождением файловых блокировок
 * @param {Object} track - трек для удаления
 * @param {number} trackIndex - индекс трека в очереди
 * @param {Object} context - контекст выполнения
 */
export async function deleteTrack(track, trackIndex, context) {
    const { 
        queue, tracks, currentIndex, media, playIndex, renderList, 
        showNotification, loadTrack 
    } = context;
    
    try {
        // Confirm deletion
        const confirmMessage = `Delete track "${track.name.replace(/\s*\[.*?\]$/, '')}" from playlist?\n\nTrack will be moved to trash and can be restored.`;
        if (!confirm(confirmMessage)) {
            return;
        }
        
        console.log(`🗑️ Deleting track: ${track.name} (${track.video_id})`);
        
        // CRITICAL: File lock release logic (используется всегда для надежности)
        let wasCurrentTrack = false;
        let currentTime = 0;
        
        if (trackIndex === currentIndex && !media.paused) {
            wasCurrentTrack = true;
            console.log('🔓 Deleting currently playing track - releasing file lock...');
            
            // Pause and clear media source to release file lock
            media.pause();
            currentTime = media.currentTime; // Save position for potential restore
            media.src = ''; // This releases the file lock
            media.load(); // Ensure the media element is properly reset
            
            console.log('🔓 Media file released, proceeding with deletion...');
            
            // Give a small delay to ensure file is fully released
            await new Promise(resolve => setTimeout(resolve, 200));
        }
        
        // Send delete request to API
        const response = await fetch('/api/channels/delete_track', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                video_id: track.video_id
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'ok') {
            console.log(`✅ Track deleted successfully: ${result.message}`);
            
            // Remove track from current queue
            queue.splice(trackIndex, 1);
            
            // Also remove from original tracks array
            const originalIndex = tracks.findIndex(t => t.video_id === track.video_id);
            if (originalIndex !== -1) {
                tracks.splice(originalIndex, 1);
            }
            
            // Adjust current index if needed
            const currentIdx = context.getCurrentIndex ? context.getCurrentIndex() : context.currentIndex;
            if (trackIndex < currentIdx) {
                // Track deleted before current position - shift current index back
                if (context.setCurrentIndex) {
                    context.setCurrentIndex(currentIdx - 1);
                } else {
                    context.currentIndex--;
                }
            } else if (trackIndex === currentIdx) {
                // If we deleted the currently playing track
                if (queue.length > 0) {
                    // Play the next track or the first one if we were at the end
                    const nextIndex = trackIndex < queue.length ? trackIndex : 0;
                    playIndex(nextIndex);
                } else {
                    // No tracks left - универсальная логика
                    media.pause();
                    media.src = '';
                    if (context.setCurrentIndex) {
                        context.setCurrentIndex(-1);
                    } else {
                        context.currentIndex = -1;
                    }
                    showNotification('📭 Playlist is empty - all tracks deleted', 'info');
                }
            }
            
            // Update the list display
            renderList();
            
            // Show success message
            showNotification(`✅ Track deleted: ${result.message}`, 'success');
            
        } else {
            console.error('❌ Failed to delete track:', result.error);
            showNotification(`❌ Deletion error: ${result.error}`, 'error');
            
            // On failure, try to restore playback if it was the current track (универсальная логика)
            if (wasCurrentTrack) {
                console.log('🔄 Attempting to restore playback after deletion failure...');
                try {
                    loadTrack(currentIndex, true);
                    if (currentTime && isFinite(currentTime)) {
                        setTimeout(() => {
                            media.currentTime = currentTime; // Restore position
                        }, 500);
                    }
                } catch (restoreError) {
                    console.warn('⚠️ Could not restore playback:', restoreError);
                }
            }
        }
        
    } catch (error) {
        console.error('❌ Error deleting track:', error);
        showNotification(`❌ Network error: ${error.message}`, 'error');
        
        // On error, try to restore playback (универсальная логика)
        if (wasCurrentTrack && trackIndex === context.currentIndex) {
            console.log('🔄 Attempting to restore playback after network error...');
            try {
                loadTrack(context.currentIndex, true);
                if (currentTime && isFinite(currentTime)) {
                    setTimeout(() => {
                        media.currentTime = currentTime; // Restore position
                    }, 500);
                }
            } catch (restoreError) {
                console.warn('⚠️ Could not restore playback:', restoreError);
            }
        }
    }
} 

// ==============================
// GOOGLE CAST INTEGRATION
// ==============================

/**
 * Инициализирует интеграцию с Google Cast
 * @param {Object} context - контекст выполнения
 * @param {number} context.currentIndex - текущий индекс трека
 * @param {Array} context.queue - очередь треков
 * @param {Function} context.castLoad - функция загрузки трека на Cast устройство
 * @returns {Object} - возвращает объекты castContext и pendingCastTrack для использования
 */
export function initializeGoogleCastIntegration(context) {
    const { currentIndex, queue, castLoad } = context;
    
    console.log('🔄 CAST DEBUG: Starting Google Cast integration setup...');
    
    let castContext = null;
    let pendingCastTrack = null;

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
    
    // Return the context objects for external usage
    return { castContext, pendingCastTrack, setCastContext: (ctx) => { castContext = ctx; }, setPendingCastTrack: (track) => { pendingCastTrack = track; } };
}

/**
 * Загружает трек на Google Cast устройство
 * @param {Object} track - трек для загрузки
 * @param {Object} castState - состояние Cast (castContext, pendingCastTrack, setPendingCastTrack)
 */
export function castLoad(track, castState) {
    const { castContext, setPendingCastTrack } = castState;
    
    console.log('🎵 CAST DEBUG: castLoad() called for track:', track.name);
    
    if(!castContext) {
        console.warn('❌ CAST DEBUG: No cast context available for loading track');
        return;
    }
    
    console.log('🔄 CAST DEBUG: Getting current cast session...');
    const session = castContext.getCurrentSession();
    if(!session){
        console.log('📝 CAST DEBUG: No active session, saving track as pending');
        setPendingCastTrack(track);
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

/**
 * Загружает трек в плеер с полной настройкой метаданных и событий
 * @param {number} idx - индекс трека для загрузки
 * @param {boolean} autoplay - автоматически начать воспроизведение
 * @param {Object} context - контекст выполнения
 */
export function loadTrack(idx, autoplay = false, context) {
    const { 
        queue, currentIndex, setCurrentIndex, media, speedOptions, currentSpeedIndex,
        castLoad, renderList, cLike, cDislike, reportEvent, sendStreamEvent
    } = context;
    
    if(idx < 0 || idx >= queue.length) return;
    setCurrentIndex(idx);
    const track = queue[idx];
    media.src = track.url;
    if(autoplay) {
        media.play();
    } else {
        media.load();
    }
    
    // Preserve playback speed when loading new track
    media.playbackRate = speedOptions[currentSpeedIndex];
    
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
    let likedCurrent = false;
    cLike.classList.remove('like-active');
    cLike.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>';
    cDislike.classList.remove('dislike-active');
    cDislike.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z"></path></svg>';
    // report play start once per track
    reportEvent(track.video_id, 'start');
    sendStreamEvent({action:'seek', idx: currentIndex, paused: media.paused, position: media.currentTime});
} 

// ===================================
// 11. EVENT HANDLERS & MEDIA CONTROLS
// ===================================

/**
 * Sets up media ended event handler - handles track completion and auto-advance
 * @param {HTMLMediaElement} media - Audio/video element
 * @param {Object} context - Player context
 * @param {Array} context.queue - Current queue of tracks
 * @param {number|Function} context.currentIndex - Current track index (value or function)
 * @param {Function} context.reportEvent - Event reporting function
 * @param {Function} context.triggerAutoDeleteCheck - Auto-delete check function
 * @param {Function} context.playIndex - Play track by index function
 */
export function setupMediaEndedHandler(media, context) {
  media.addEventListener('ended', () => {
    // Get current index - handle both function and direct value
    const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
    
    // capture current track before any change
    const finishedTrack = context.queue[currentIndex];

    // report finish first
    if (finishedTrack) {
      context.reportEvent(finishedTrack.video_id, 'finish');
      
      // Trigger auto-delete check for channel content
      context.triggerAutoDeleteCheck(finishedTrack);
    }

    // then move to next track if available
    if (currentIndex + 1 < context.queue.length) {
      console.log(`🎵 Auto-advancing from track ${currentIndex} to ${currentIndex + 1}`);
      context.playIndex(currentIndex + 1);
    } else {
      console.log(`🏁 Reached end of queue at track ${currentIndex}, no more tracks to play`);
    }
  });
}

/**
 * Sets up media play/pause event handlers - manages UI icons and event reporting
 * @param {HTMLMediaElement} media - Audio/video element
 * @param {Object} context - Player context
 * @param {HTMLElement} context.cPlay - Play/pause button element
 * @param {Array} context.queue - Current queue of tracks
 * @param {number} context.currentIndex - Current track index
 * @param {Function} context.reportEvent - Event reporting function
 */
export function setupMediaPlayPauseHandlers(media, context) {
  media.addEventListener('play', () => {
    // Change to pause icon
    context.cPlay.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>';
    // Report play/resume event with current position
    if(context.currentIndex >= 0 && context.currentIndex < context.queue.length) {
      const track = context.queue[context.currentIndex];
      context.reportEvent(track.video_id, 'play', media.currentTime);
    }
  });
  
  media.addEventListener('pause', () => {
    // Change to play icon
    context.cPlay.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
    // Report pause event with current position
    if(context.currentIndex >= 0 && context.currentIndex < context.queue.length) {
      const track = context.queue[context.currentIndex];
      context.reportEvent(track.video_id, 'pause', media.currentTime);
    }
  });
}

/**
 * Sets up media timeupdate handler - updates progress bar and time display
 * @param {HTMLMediaElement} media - Audio/video element
 * @param {Object} context - Player context
 * @param {HTMLElement} context.progressBar - Progress bar element
 * @param {HTMLElement} context.timeLabel - Time label element
 * @param {Function} context.formatTime - Time formatting function
 */
export function setupMediaTimeUpdateHandler(media, context) {
  media.addEventListener('timeupdate', () => {
    const percent = (media.currentTime / media.duration) * 100;
    context.progressBar.style.width = `${percent}%`;
    context.timeLabel.textContent = `${context.formatTime(media.currentTime)} / ${context.formatTime(media.duration)}`;
  });
}

/**
 * Sets up media seeked handler - records seek events for analytics
 * @param {HTMLMediaElement} media - Audio/video element
 * @param {Object} context - Player context with seek state
 * @param {Array} context.queue - Current queue of tracks
 * @param {number|Function} context.currentIndex - Current track index (value or function)
 * @param {Function} context.recordSeekEvent - Seek event recording function
 * @param {Object} context.seekState - Seek state object (seekStartPosition)
 */
export function setupMediaSeekedHandler(media, context) {
  media.addEventListener('seeked', () => {
    // Get current index - handle both function and direct value
    const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
    
    if (context.seekState.seekStartPosition !== null && currentIndex >= 0 && currentIndex < context.queue.length) {
      const track = context.queue[currentIndex];
      const seekTo = media.currentTime;
      
      // Only record meaningful seeks (> 1 second difference)
      if (Math.abs(seekTo - context.seekState.seekStartPosition) >= 1.0) {
        console.log(`⏩ Seek recorded: ${Math.round(context.seekState.seekStartPosition)}s → ${Math.round(seekTo)}s for track "${track.name}"`);
        context.recordSeekEvent(track.video_id, context.seekState.seekStartPosition, seekTo, 'progress_bar');
      }
      
      context.seekState.seekStartPosition = null; // Reset
    }
  });
}

/**
 * Sets up keyboard event handler - handles all keyboard shortcuts
 * @param {Object} context - Player context
 * @param {Function} context.performKeyboardSeek - Keyboard seek function
 * @param {Function} context.nextTrack - Next track function
 * @param {Function} context.prevTrack - Previous track function
 * @param {Function} context.togglePlayback - Toggle playback function
 */
export function setupKeyboardHandler(context) {
  // Keyboard shortcuts: ← prev, → next, Space play/pause, Arrow Up/Down for seek
  document.addEventListener('keydown', (e) => {
    switch (e.code) {
      case 'ArrowRight':
        if (e.shiftKey) {
          // Shift + Right = Seek forward 10 seconds
          e.preventDefault();
          context.performKeyboardSeek(10);
        } else {
          context.nextTrack();
        }
        break;
      case 'ArrowLeft':
        if (e.shiftKey) {
          // Shift + Left = Seek backward 10 seconds
          e.preventDefault();
          context.performKeyboardSeek(-10);
        } else {
          context.prevTrack();
        }
        break;
      case 'ArrowUp':
        e.preventDefault();
        context.performKeyboardSeek(30); // Seek forward 30 seconds
        break;
      case 'ArrowDown':
        e.preventDefault();
        context.performKeyboardSeek(-30); // Seek backward 30 seconds
        break;
      case 'Space':
        e.preventDefault();
        context.togglePlayback();
        break;
    }
  });
}

/**
 * Sets up progress container click handler - handles seeking via progress bar clicks
 * @param {HTMLElement} progressContainer - Progress container element
 * @param {HTMLMediaElement} media - Audio/video element
 * @param {Object} context - Player context
 * @param {number|Function} context.currentIndex - Current track index (value or function)
 * @param {Function} context.sendStreamEvent - Stream event function
 * @param {Object} context.seekState - Seek state object (seekStartPosition)
 */
export function setupProgressClickHandler(progressContainer, media, context) {
  // Progress bar click handling with seek tracking
  progressContainer.onclick = (e) => {
    const rect = progressContainer.getBoundingClientRect();
    const pos = (e.clientX - rect.left) / rect.width;
    
    // Get current index - handle both function and direct value
    const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
    
    // Store seek start position
    context.seekState.seekStartPosition = media.currentTime;
    
    // Perform seek
    media.currentTime = pos * media.duration;
    
    // Send stream event
    context.sendStreamEvent({action:'seek', idx: currentIndex, paused: media.paused, position: media.currentTime});
    
    // Record seek event will happen in 'seeked' event listener
  };
}

/**
 * Sets up Media Session API handlers - enables media key controls
 * @param {Object} context - Player context
 * @param {Function} context.prevTrack - Previous track function
 * @param {Function} context.nextTrack - Next track function
 * @param {HTMLMediaElement} context.media - Audio/video element
 */
export function setupMediaSessionAPI(context) {
  // ---- Media Session API ----
  if ('mediaSession' in navigator) {
    navigator.mediaSession.setActionHandler('previoustrack', () => context.prevTrack());
    navigator.mediaSession.setActionHandler('nexttrack', () => context.nextTrack());
    navigator.mediaSession.setActionHandler('play', () => context.media.play());
    navigator.mediaSession.setActionHandler('pause', () => context.media.pause());
  }
}

/**
 * Sets up playlist toggle button handler - controls playlist visibility
 * @param {HTMLElement} toggleListBtn - Toggle list button element
 * @param {HTMLElement} playlistPanel - Playlist panel element
 */
export function setupPlaylistToggleHandler(toggleListBtn, playlistPanel) {
  // Playlist collapse/expand
  toggleListBtn.onclick = () => {
    playlistPanel.classList.toggle('collapsed');
    toggleListBtn.textContent = playlistPanel.classList.contains('collapsed') ? '☰ Show playlist' : '☰ Hide playlist';
  };
} 

// ===== 12. UI INTERACTIONS & CONTROL HANDLERS =====

/**
 * Настраивает обработчик кнопки удаления текущего трека
 * @param {HTMLElement} deleteCurrentBtn - кнопка удаления
 * @param {Object} context - контекст с необходимыми данными
 * @param {Object} context.currentIndex - текущий индекс
 * @param {Array} context.queue - очередь треков  
 * @param {Array} context.tracks - массив треков
 * @param {HTMLElement} context.media - медиа элемент
 * @param {Function} context.playIndex - функция воспроизведения по индексу
 * @param {Function} context.renderList - функция обновления списка
 * @param {Function} context.showNotification - функция показа уведомлений
 * @param {Function} context.loadTrack - функция загрузки трека
 * @param {string} playerType - тип плеера ('regular' или 'virtual')
 */
export function setupDeleteCurrentHandler(deleteCurrentBtn, context, playerType = 'regular') {
    if (!deleteCurrentBtn) return;

    deleteCurrentBtn.onclick = async () => {
        // Get current index value (handle both direct values and functions)
        const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
        
        // Check if there's a current track
        if (currentIndex < 0 || currentIndex >= context.queue.length) {
            context.showNotification('❌ No active track to delete', 'error');
            return;
        }
        
        const currentTrack = context.queue[currentIndex];
        
        // Confirm deletion
        const confirmMessage = `Delete current track "${currentTrack.name.replace(/\s*\[.*?\]$/, '')}" from playlist?\n\nTrack will be moved to trash and can be restored.`;
        if (!confirm(confirmMessage)) {
            return;
        }
        
        console.log(`🗑️ Deleting current track: ${currentTrack.name} (${currentTrack.video_id})`);
        
        try {
            // CRITICAL: First pause and clear media source to release file lock
            context.media.pause();
            const currentTime = context.media.currentTime; // Save position for potential restore
            context.media.src = ''; // This releases the file lock
            context.media.load(); // Ensure the media element is properly reset
            
            console.log('🔓 Media file released, proceeding with deletion...');
            
            // Give a small delay to ensure file is fully released
            await new Promise(resolve => setTimeout(resolve, 200));
            
            // Send delete request to API
            const response = await fetch('/api/channels/delete_track', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    video_id: currentTrack.video_id
                })
            });
            
            const result = await response.json();
            
            if (result.status === 'ok') {
                const successMessage = playerType === 'regular' ? 
                    `✅ Current track deleted successfully: ${result.message}` : 
                    `✅ Track deleted successfully: ${result.message}`;
                console.log(successMessage);
                
                // Remove track from current queue
                context.queue.splice(currentIndex, 1);
                
                // Also remove from original tracks array
                const originalIndex = context.tracks.findIndex(t => t.video_id === currentTrack.video_id);
                if (originalIndex !== -1) {
                    context.tracks.splice(originalIndex, 1);
                }
                
                // Handle playback continuation
                if (context.queue.length > 0) {
                    // Stay at the same index if possible, or go to first track
                    const nextIndex = currentIndex < context.queue.length ? currentIndex : 0;
                    console.log(`🎵 Auto-continuing to next track at index ${nextIndex}`);
                    context.playIndex(nextIndex);
                } else {
                    // No tracks left - note: cannot modify currentIndex directly as it might be a function result
                    context.showNotification('📭 Playlist is empty - all tracks deleted', 'info');
                }
                
                // Update the list display
                context.renderList();
                
                // Show success message
                context.showNotification(`✅ Track deleted: ${result.message}`, 'success');
                
            } else {
                const errorType = playerType === 'regular' ? 'current track' : 'track';
                console.error(`❌ Failed to delete ${errorType}:`, result.error);
                context.showNotification(`❌ Deletion error: ${result.error}`, 'error');
                
                // On failure, try to restore playback of the same track
                console.log('🔄 Attempting to restore playback after deletion failure...');
                try {
                    context.loadTrack(currentIndex, true);
                    if (currentTime && isFinite(currentTime)) {
                        setTimeout(() => {
                            context.media.currentTime = currentTime; // Restore position
                        }, 500);
                    }
                } catch (restoreError) {
                    console.warn('⚠️ Could not restore playback:', restoreError);
                }
            }
            
        } catch (error) {
            const errorType = playerType === 'regular' ? 'current track' : 'track';
            console.error(`❌ Error deleting ${errorType}:`, error);
            context.showNotification(`❌ Network error: ${error.message}`, 'error');
            
            // On error, try to restore playback
            console.log('🔄 Attempting to restore playback after network error...');
            try {
                context.loadTrack(currentIndex, true);
                if (currentTime && isFinite(currentTime)) {
                    setTimeout(() => {
                        context.media.currentTime = currentTime; // Restore position
                    }, 500);
                }
            } catch (restoreError) {
                console.warn('⚠️ Could not restore playback:', restoreError);
            }
        }
    };
}

/**
 * Настраивает обработчики кнопок лайка и дизлайка
 * @param {HTMLElement} cLike - кнопка лайка
 * @param {HTMLElement} cDislike - кнопка дизлайка
 * @param {Object} context - контекст с необходимыми данными
 * @param {Object} context.currentIndex - текущий индекс
 * @param {Array} context.queue - очередь треков
 * @param {HTMLElement} context.media - медиа элемент
 * @param {Function} context.reportEvent - функция отправки событий
 * @param {Object} context.likedCurrent - состояние лайка (по ссылке)
 */
export function setupLikeDislikeHandlers(cLike, cDislike, context) {
    if (cLike) {
        cLike.onclick = () => {
            const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
            if (currentIndex < 0 || currentIndex >= context.queue.length) return;
            const track = context.queue[currentIndex];
            context.reportEvent(track.video_id, 'like', context.media.currentTime);
            context.likedCurrent = true;
            cLike.classList.add('like-active');
            // Change to filled heart (same icon, but red styling via CSS class)
            cLike.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>';
        };
    }

    if (cDislike) {
        cDislike.onclick = () => {
            const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
            if (currentIndex < 0 || currentIndex >= context.queue.length) return;
            const track = context.queue[currentIndex];
            context.reportEvent(track.video_id, 'dislike', context.media.currentTime);
            cDislike.classList.add('dislike-active');
            // Change to filled dislike (same icon, but purple styling via CSS class)
            cDislike.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z"></path></svg>';
        };
    }
}

/**
 * Настраивает обработчик кнопки YouTube
 * @param {HTMLElement} cYoutube - кнопка YouTube
 * @param {Object} context - контекст с необходимыми данными
 * @param {Object} context.currentIndex - текущий индекс
 * @param {Array} context.queue - очередь треков
 */
export function setupYouTubeHandler(cYoutube, context) {
    if (cYoutube) {
        cYoutube.onclick = () => {
            const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
            if (currentIndex < 0 || currentIndex >= context.queue.length) return;
            const track = context.queue[currentIndex];
            if (track.video_id) {
                const youtubeUrl = `https://www.youtube.com/watch?v=${track.video_id}`;
                window.open(youtubeUrl, '_blank');
            } else {
                console.warn('No video_id found for current track');
            }
        };
    }
}

/**
 * Настраивает обработчики полноэкранных кнопок
 * @param {HTMLElement} fullBtn - кнопка полноэкранного режима (основная)
 * @param {HTMLElement} cFull - кнопка полноэкранного режима (в контролах)
 * @param {HTMLElement} wrapper - контейнер для полноэкранного режима
 */
export function setupFullscreenHandlers(fullBtn, cFull, wrapper) {
    const fullscreenHandler = () => {
        if (!document.fullscreenElement) {
            wrapper.requestFullscreen?.() || wrapper.webkitRequestFullscreen?.();
        } else {
            document.exitFullscreen?.() || document.webkitExitFullscreen?.();
        }
    };

    if (fullBtn) {
        fullBtn.onclick = fullscreenHandler;
    }

    if (cFull) {
        cFull.onclick = fullscreenHandler;
    }
}

/**
 * Настраивает обработчики простых кнопок управления
 * @param {HTMLElement} cPrev - кнопка предыдущего трека
 * @param {HTMLElement} cNext - кнопка следующего трека
 * @param {HTMLElement} media - медиа элемент
 * @param {Function} prevTrack - функция предыдущего трека
 * @param {Function} nextTrack - функция следующего трека
 * @param {Function} togglePlayback - функция переключения воспроизведения
 */
export function setupSimpleControlHandlers(cPrev, cNext, media, prevTrack, nextTrack, togglePlayback) {
    if (cPrev) {
        cPrev.onclick = () => prevTrack();
    }

    if (cNext) {
        cNext.onclick = () => nextTrack();
    }

    // Clicking on the video toggles play/pause
    if (media) {
        media.addEventListener('click', togglePlayback);
    }
}

/**
 * Настраивает обработчик кнопки стриминга
 * @param {HTMLElement} streamBtn - кнопка стриминга (может быть null в virtual плеере)
 * @param {Object} context - контекст с необходимыми данными
 * @param {Object} context.streamIdLeader - ID текущего стрима
 * @param {Array} context.queue - очередь треков
 * @param {Object} context.currentIndex - текущий индекс
 * @param {HTMLElement} context.media - медиа элемент
 * @param {Function} context.sendStreamEvent - функция отправки событий стрима
 * @param {Function} context.startTick - функция запуска таймера
 */
export function setupStreamHandler(streamBtn, context) {
    if (streamBtn) {
        streamBtn.onclick = async () => {
            const streamIdLeader = typeof context.streamIdLeader === 'function' ? context.streamIdLeader() : context.streamIdLeader;
            const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
            
            if (streamIdLeader) {
                alert('Stream already running. Share this URL:\n' + window.location.origin + '/stream/' + streamIdLeader);
                return;
            }
            const title = prompt('Stream title:', document.title);
            if (title === null) return;
            try {
                const body = {
                    title,
                    queue: context.queue,
                    idx: currentIndex,
                    paused: context.media.paused,
                    position: context.media.currentTime
                };
                const res = await fetch('/api/create_stream', { 
                    method: 'POST', 
                    headers: { 'Content-Type': 'application/json' }, 
                    body: JSON.stringify(body) 
                });
                const data = await res.json();
                // Note: Cannot set streamIdLeader directly if it's from a function - handled by caller
                streamBtn.textContent = 'Streaming…';
                streamBtn.disabled = true;
                if (!context.media.paused) {
                    context.sendStreamEvent({ action: 'play', position: context.media.currentTime, paused: false });
                    context.startTick();
                }
                const overlay = document.getElementById('shareOverlay');
                const linkEl = document.getElementById('shareLink');
                linkEl.href = data.url;
                linkEl.textContent = data.url;
                overlay.style.display = 'block';
                const copyBtn = document.getElementById('copyLinkBtn');
                copyBtn.onclick = () => {
                    if (!context.media.paused) { 
                        context.sendStreamEvent({ action: 'play' }); 
                    } // notify listeners to start
                    navigator.clipboard.writeText(data.url).catch(() => {});
                };
                document.getElementById('closeShare').onclick = () => overlay.style.display = 'none';
            } catch (err) { 
                alert('Stream creation failed: ' + err); 
            }
        };
    } else {
        console.warn('🔍 [DEBUG] streamBtn not found, streaming functionality disabled');
    }
}

/**
 * Настраивает обработчик window beforeunload для остановки tick при закрытии
 * @param {Function} stopTick - функция остановки таймера
 */
export function setupBeforeUnloadHandler(stopTick) {
    window.addEventListener('beforeunload', () => stopTick());
}

/**
 * Настраивает автозапуск воспроизведения и синхронизацию
 * @param {Array} queue - очередь треков
 * @param {Function} playIndex - функция воспроизведения по индексу
 * @param {Function} renderList - функция обновления списка
 * @param {Function} syncRemoteState - функция синхронизации состояния
 */
export function setupAutoPlayInitialization(queue, playIndex, renderList, syncRemoteState) {
    // auto smart-shuffle and start playback on first load
    if (queue.length > 0) {
        playIndex(0);
        // Force sync after initial load
        setTimeout(syncRemoteState, 500);
    } else {
        renderList();
    }
}

/**
 * Настраивает переопределения функций для remote синхронизации
 * @param {Function} playIndex - исходная функция воспроизведения
 * @param {Function} togglePlayback - исходная функция переключения воспроизведения
 * @param {Function} syncRemoteState - функция синхронизации состояния
 */
export function setupRemoteControlOverrides(playIndex, togglePlayback, syncRemoteState) {
    // Override existing functions to include remote sync
    const originalPlayIndex = playIndex;
    window.playIndex = function(idx) {
        originalPlayIndex.call(this, idx);
        setTimeout(syncRemoteState, 200);
    };
    
    const originalTogglePlayback = togglePlayback;
    window.togglePlayback = function() {
        originalTogglePlayback.call(this);
        setTimeout(syncRemoteState, 200);
    };
}

/**
 * Настраивает инициализацию remote control синхронизации
 * @param {HTMLElement} media - медиа элемент
 * @param {Function} syncRemoteState - функция синхронизации состояния
 * @param {Function} pollRemoteCommands - функция опроса команд
 * @param {Object} context - контекст с текущим индексом
 */
export function setupRemoteControlInitialization(media, syncRemoteState, pollRemoteCommands, context) {
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
    
    // Initial state sync after everything is loaded
    setTimeout(() => {
        const currentIndex = typeof context.currentIndex === 'function' ? context.currentIndex() : context.currentIndex;
        if (currentIndex >= 0) {
            syncRemoteState();
        }
        // Start periodic sync every 3 seconds
        setInterval(syncRemoteState, 3000);
    }, 1000);
    
    // Periodic remote command polling (every 1 second)
    setInterval(pollRemoteCommands, 1000);
    
    console.log('🎮 Remote control synchronization initialized');
}