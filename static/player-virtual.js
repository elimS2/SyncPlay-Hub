async function fetchTracks(playlistPath = '') {
  // For virtual playlists, get like count from global variable
  const likeCount = typeof VIRTUAL_PLAYLIST_LIKE_COUNT !== 'undefined' ? VIRTUAL_PLAYLIST_LIKE_COUNT : 1;
  
  console.log(`🔍 [Virtual] fetchTracks called for ${likeCount} likes`);
  
  try {
    const response = await fetch(`/api/tracks_by_likes/${likeCount}`);
    const data = await response.json();
    
    if (data.status === 'ok') {
      console.log(`✅ [Virtual] Successfully loaded ${data.tracks.length} tracks with ${likeCount} likes`);
      console.log(`📋 [Virtual] Track sample:`, data.tracks.slice(0, 3).map(t => t.name));
      return data.tracks;
    } else {
      throw new Error(data.message || 'API Error');
    }
  } catch (error) {
    console.error('❌ [Virtual] Error loading tracks:', error);
    return [];
  }
}

function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
}

// ===== SMART CHANNEL PLAYBACK LOGIC =====

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

function detectChannelGroup(track) {
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

function smartChannelShuffle(tracks) {
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

function orderByPublishDate(tracks) {
  /**
   * Sort tracks by YouTube publish date in ascending order (oldest first)
   * Uses timestamp, release_timestamp, or release_year from virtual playlist API
   */
  if (!tracks || tracks.length === 0) return [];

  const orderedTracks = [...tracks];
  
  orderedTracks.sort((a, b) => {
    // Get publish dates for comparison
    const getPublishTimestamp = (track) => {
      // Priority: timestamp > release_timestamp > release_year > fallback to 0
      if (track.timestamp && track.timestamp > 0) {
        return track.timestamp;
      }
      if (track.release_timestamp && track.release_timestamp > 0) {
        return track.release_timestamp;
      }
      if (track.release_year && track.release_year > 0) {
        // Convert year to approximate timestamp (January 1st of that year)
        return new Date(`${track.release_year}-01-01`).getTime() / 1000;
      }
      // Fallback for tracks without date info - put them at the beginning
      return 0;
    };

    const aTime = getPublishTimestamp(a);
    const bTime = getPublishTimestamp(b);
    
    // Sort ascending (oldest first)
    return aTime - bTime;
  });

  console.log(`📅 [Virtual] Tracks ordered by publish date (oldest first): ${orderedTracks.length} tracks`);
  
  // Debug log first few tracks to verify sorting
  if (orderedTracks.length > 0) {
    console.log('📅 [Virtual] First few tracks by date:');
    orderedTracks.slice(0, 3).forEach((track, idx) => {
      const date = track.timestamp ? new Date(track.timestamp * 1000).toLocaleDateString() :
                   track.release_timestamp ? new Date(track.release_timestamp * 1000).toLocaleDateString() :
                   track.release_year ? track.release_year : 'Unknown';
      console.log(`  ${idx + 1}. ${track.name} (${date})`);
    });
  }

  return orderedTracks;
}

function getGroupPlaybackInfo(tracks) {
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

// ===== END SMART CHANNEL PLAYBACK LOGIC =====

(async () => {
  const media = document.getElementById('player');
  const listElem = document.getElementById('tracklist');
  const shuffleBtn = document.getElementById('shuffleBtn');
  const smartShuffleBtn = document.getElementById('smartShuffleBtn');
  const deleteCurrentBtn = document.getElementById('deleteCurrentBtn');
  const fullBtn = document.getElementById('fullBtn');
  const cLike = document.getElementById('cLike');
const cDislike = document.getElementById('cDislike');
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
  const cSpeed = document.getElementById('cSpeed');
  const speedLabel = document.getElementById('speedLabel');
  const toggleListBtn = document.getElementById('toggleListBtn');
  const playlistPanel = document.getElementById('playlistPanel');
  const controlBar = document.getElementById('controlBar');
  const customControls = document.getElementById('customControls');
  let fsTimer;
  const streamBtn = document.getElementById('streamBtn');
  let streamIdLeader = null;
  let tickTimer=null;

  // Playback speed control
  const speedOptions = [0.5, 0.75, 1, 1.25, 1.5, 2];
  let currentSpeedIndex = 2; // Default to 1x (index 2)

  const playlistRel = typeof PLAYLIST_REL !== 'undefined' ? PLAYLIST_REL : '';
  let tracks = await fetchTracks(playlistRel);

  let queue = smartChannelShuffle([...tracks]);
  let currentIndex = -1;
  
  // Log playback info
  const playbackInfo = getGroupPlaybackInfo(tracks);
  if (playbackInfo && playbackInfo.length > 0) {
    console.log('🎯 Smart Playback Info:');
    playbackInfo.forEach(info => {
      const icon = info.type === 'music' ? '🎵' : 
                   info.type === 'news' ? '📰' : 
                   info.type === 'education' ? '🎓' : 
                   info.type === 'podcasts' ? '🎙️' : '📋';
      console.log(`  ${icon} ${info.group}: ${info.count} tracks (${info.isChannel ? 'Channel' : 'Playlist'})`);
    });
  }

  if (tracks.length === 0) {
    console.warn('❌ No tracks loaded - check API endpoint');
  } else if (queue.length === 0) {
    console.warn('❌ Queue is empty - check smartChannelShuffle function');
  } else {
    console.log('✅ Data looks good, rendering playlist...');
    renderList();
    console.log('✅ Playlist rendered successfully');
  }

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

  console.log('🔍 [DEBUG] Cast integration completed, starting main player logic...');

  function renderList() {
    listElem.innerHTML = '';
    queue.forEach((t, idx) => {
      const li = document.createElement('li');
      li.dataset.index = idx;
      if (idx === currentIndex) li.classList.add('playing');
      
      // Prepare tooltip content with track metadata and statistics
      const publishDate = t.timestamp ? new Date(t.timestamp * 1000).toLocaleDateString() : 'Unknown';
      const lastPlayDate = t.last_play ? new Date(t.last_play + 'Z').toLocaleDateString() : 'Never';
      const playCount = t.play_starts || 0;
      const completeCount = t.play_finishes || 0;
      const nextCount = t.play_nexts || 0;
      const likeCount = t.play_likes || 0;
      const dislikeCount = t.play_dislikes || 0;
      
      // Debug: tooltip data prepared for track
      
      const tooltipContent = `
        <div class="tooltip-row">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="16" y1="2" x2="16" y2="6"></line>
            <line x1="8" y1="2" x2="8" y2="6"></line>
            <line x1="3" y1="10" x2="21" y2="10"></line>
          </svg>
          <strong>Published:</strong> ${publishDate}
        </div>
        <div class="tooltip-row">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12,6 12,12 16,14"></polyline>
          </svg>
          <strong>Last Played:</strong> ${lastPlayDate}
        </div>
        <div class="tooltip-section">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 18V5l12-2v13"></path>
            <circle cx="6" cy="18" r="3"></circle>
            <circle cx="18" cy="16" r="3"></circle>
          </svg>
          <strong>Statistics</strong>
        </div>
        <div class="tooltip-row">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5,3 19,12 5,21"></polygon>
          </svg>
          Total Plays: ${playCount}
        </div>
        <div class="tooltip-row">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 12l2 2 4-4"></path>
            <path d="M21 12c-1 0-3-1-3-3s2-3 3-3 3 1 3 3-2 3-3 3"></path>
            <path d="M3 12c1 0 3-1 3-3s-2-3-3-3-3 1-3 3 2 3 3 3"></path>
          </svg>
          Completed: ${completeCount}
        </div>
        <div class="tooltip-row">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5,4 15,12 5,20"></polygon>
            <line x1="19" y1="5" x2="19" y2="19"></line>
          </svg>
          Next Clicks: ${nextCount}
        </div>
        <div class="tooltip-row">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
          </svg>
          Likes: ${likeCount}
        </div>
        <div class="tooltip-row">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9b59b6" stroke-width="2">
            <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z"></path>
          </svg>
          Dislikes: ${dislikeCount}
        </div>
      `;
      
      li.dataset.tooltipHtml = tooltipContent;
      
      // Create track content container
      const trackContent = document.createElement('div');
      trackContent.className = 'track-content';
      trackContent.style.cssText = 'display: flex; justify-content: space-between; align-items: center; width: 100%;';
      
      // Track name and number
      const trackInfo = document.createElement('div');
      trackInfo.className = 'track-info';
      trackInfo.style.cssText = 'flex: 1; cursor: pointer;';
      const displayName = t.name.replace(/\s*\[.*?\]$/, '');
      trackInfo.textContent = `${idx + 1}. ${displayName}`;
      trackInfo.onclick = () => playIndex(idx);
      
      // Delete button
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'delete-btn';
      deleteBtn.innerHTML = '🗑️';
      deleteBtn.title = 'Delete track';
      deleteBtn.style.cssText = `
        background: none;
        border: none;
        color: #ff4444;
        cursor: pointer;
        font-size: 16px;
        padding: 4px 8px;
        border-radius: 4px;
        margin-left: 8px;
        opacity: 0.7;
        transition: opacity 0.2s ease, background-color 0.2s ease;
      `;
      
      // Hover effects for delete button
      deleteBtn.onmouseenter = () => {
        deleteBtn.style.opacity = '1';
        deleteBtn.style.backgroundColor = 'rgba(255, 68, 68, 0.1)';
      };
      deleteBtn.onmouseleave = () => {
        deleteBtn.style.opacity = '0.7';
        deleteBtn.style.backgroundColor = 'transparent';
      };
      
      deleteBtn.onclick = (e) => {
        e.stopPropagation(); // Prevent track selection
        deleteTrack(t, idx);
      };
      
      trackContent.appendChild(trackInfo);
      trackContent.appendChild(deleteBtn);
      li.appendChild(trackContent);
      listElem.appendChild(li);
    });
    
    console.log(`🎵 Rendered ${queue.length} tracks in playlist`);
    
    // Create global tooltip system (like in player.js)
    setupGlobalTooltip();
  }

  function loadTrack(idx, autoplay=false){
    if(idx<0 || idx>=queue.length) return;
    currentIndex=idx;
    const track=queue[currentIndex];
    media.src=track.url;
    if(autoplay){media.play();}else{media.load();}
    
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
    likedCurrent=false;
    cLike.classList.remove('like-active');
    cLike.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>';
    cDislike.classList.remove('dislike-active');
    cDislike.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z"></path></svg>';
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
      
      // Trigger auto-delete check for channel content
      triggerAutoDeleteCheck(finishedTrack);
    }

    // then move to next track if available
    if (currentIndex + 1 < queue.length) {
      playIndex(currentIndex + 1);
    }
  });

  shuffleBtn.onclick = () => {
    // Regular random shuffle
    queue = [...tracks];
    shuffle(queue);
    console.log('🔀 Random shuffle applied to all tracks');
    playIndex(0);
  };

  smartShuffleBtn.onclick = ()=>{
     // Smart channel-aware shuffle
     queue = smartChannelShuffle([...tracks]);
     console.log('🧠 Smart channel shuffle applied');
     
     // Log playback info
     const playbackInfo = getGroupPlaybackInfo(tracks);
     if (playbackInfo && playbackInfo.length > 0) {
       console.log('🎯 Updated Playback Info:');
       playbackInfo.forEach(info => {
         const icon = info.type === 'music' ? '🎵' : 
                      info.type === 'news' ? '📰' : 
                      info.type === 'education' ? '🎓' : 
                      info.type === 'podcasts' ? '🎙️' : '📋';
         console.log(`  ${icon} ${info.group}: ${info.count} tracks (${info.isChannel ? 'Channel' : 'Playlist'})`);
       });
     }
     
     playIndex(0);
  };

  orderByDateBtn.onclick = () => {
    // Sort tracks by YouTube publish date (oldest first)
    queue = orderByPublishDate([...tracks]);
    console.log('📅 [Virtual] Tracks ordered by YouTube publish date (oldest first)');
    playIndex(0);
  };

  // Direct functions for playback control
  function stopPlayback() {
    media.pause();
    media.currentTime = 0;
  }

  function nextTrack() {
    if (currentIndex + 1 < queue.length) {
      // send event for current track before switching
      if(currentIndex>=0){ reportEvent(queue[currentIndex].video_id,'next'); }
      playIndex(currentIndex + 1);
      sendStreamEvent({action:'next', idx: currentIndex, paused: media.paused, position:0});
    }
  }

  function prevTrack() {
    if (currentIndex - 1 >= 0) {
      if(currentIndex>=0){ reportEvent(queue[currentIndex].video_id,'prev'); }
      playIndex(currentIndex - 1);
      sendStreamEvent({action:'prev', idx: currentIndex, paused: media.paused, position: media.currentTime});
    }
  }

  function togglePlayback() {
    if (media.paused) {
      media.play();
      sendStreamEvent({action:'play', position: media.currentTime, paused:false});
      startTick();
    } else {
      media.pause();
      sendStreamEvent({action:'pause', position: media.currentTime, paused:true});
    }
  }

  deleteCurrentBtn.onclick = async () => {
    // Check if there's a current track
    if (currentIndex < 0 || currentIndex >= queue.length) {
      showNotification('❌ No active track to delete', 'error');
      return;
    }
    
    const currentTrack = queue[currentIndex];
    
    // Confirm deletion
    const confirmMessage = `Delete current track "${currentTrack.name.replace(/\s*\[.*?\]$/, '')}" from playlist?\n\nTrack will be moved to trash and can be restored.`;
    if (!confirm(confirmMessage)) {
      return;
    }
    
    console.log(`🗑️ Deleting current track: ${currentTrack.name} (${currentTrack.video_id})`);
    
    try {
      // CRITICAL: First pause and clear media source to release file lock
      media.pause();
      const currentTime = media.currentTime; // Save position for potential restore
      media.src = ''; // This releases the file lock
      media.load(); // Ensure the media element is properly reset
      
      console.log('🔓 Media file released, proceeding with deletion...');
      
      // Give a small delay to ensure file is fully released
      await new Promise(resolve => setTimeout(resolve, 200));
      
      // Send delete request to API
      const response = await fetch('/api/delete_track', {
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
        console.log(`✅ Track deleted successfully: ${result.message}`);
        
        // Remove track from current queue
        queue.splice(currentIndex, 1);
        
        // Also remove from original tracks array
        const originalIndex = tracks.findIndex(t => t.video_id === currentTrack.video_id);
        if (originalIndex !== -1) {
          tracks.splice(originalIndex, 1);
        }
        
        // Handle playback continuation
        if (queue.length > 0) {
          // Stay at the same index if possible, or go to first track
          const nextIndex = currentIndex < queue.length ? currentIndex : 0;
          console.log(`🎵 Auto-continuing to next track at index ${nextIndex}`);
          playIndex(nextIndex);
        } else {
          // No tracks left
          currentIndex = -1;
          showNotification('📭 Playlist is empty - all tracks deleted', 'info');
        }
        
        // Update the list display
        renderList();
        
        // Show success message
        showNotification(`✅ Track deleted: ${result.message}`, 'success');
        
      } else {
        console.error('❌ Failed to delete track:', result.error);
        showNotification(`❌ Deletion error: ${result.error}`, 'error');
        
        // On failure, try to restore playback of the same track
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
      
    } catch (error) {
      console.error('❌ Error deleting track:', error);
      showNotification(`❌ Network error: ${error.message}`, 'error');
      
      // On error, try to restore playback
      console.log('🔄 Attempting to restore playback after network error...');
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
  };

  fullBtn.onclick = () => {
    if (!document.fullscreenElement) {
      wrapper.requestFullscreen?.() || wrapper.webkitRequestFullscreen?.();
    } else {
      document.exitFullscreen?.() || document.webkitExitFullscreen?.();
    }
  };

  cPrev.onclick = () => prevTrack();
  cNext.onclick = () => nextTrack();

  // Speed control functionality
  function updateSpeedDisplay() {
    const speed = speedOptions[currentSpeedIndex];
    if (speedLabel) {
      speedLabel.textContent = `${speed}x`;
    }
    if (cSpeed) {
      cSpeed.title = `Playback Speed: ${speed}x (click to change)`;
    }
  }

  function cyclePlaybackSpeed() {
    currentSpeedIndex = (currentSpeedIndex + 1) % speedOptions.length;
    const newSpeed = speedOptions[currentSpeedIndex];
    
    if (media) {
      media.playbackRate = newSpeed;
    }
    
    updateSpeedDisplay();
    
    console.log(`⏩ [Virtual] Playback speed changed to ${newSpeed}x`);
    
    // Report speed change event if we have a current track
    if (currentIndex >= 0 && currentIndex < queue.length) {
      const track = queue[currentIndex];
      reportEvent(track.video_id, 'speed_change', media.currentTime, { speed: newSpeed });
    }
  }

  // Initialize speed display
  updateSpeedDisplay();

  // Speed control button click handler
  if (cSpeed) {
    cSpeed.onclick = cyclePlaybackSpeed;
  }

  cPlay.onclick = togglePlayback;

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

  // Track seek events
  let lastSeekPosition = null;
  let seekStartPosition = null;
  
  // Progress bar click handling with seek tracking
  progressContainer.onclick = (e) => {
    const rect = progressContainer.getBoundingClientRect();
    const pos = (e.clientX - rect.left) / rect.width;
    
    // Store seek start position
    seekStartPosition = media.currentTime;
    
    // Perform seek
    media.currentTime = pos * media.duration;
    
    // Send stream event
    sendStreamEvent({action:'seek', idx: currentIndex, paused: media.paused, position: media.currentTime});
    
    // Record seek event will happen in 'seeked' event listener
  };
  
  // Listen for seek completion to record event
  media.addEventListener('seeked', () => {
    if (seekStartPosition !== null && currentIndex >= 0 && currentIndex < queue.length) {
      const track = queue[currentIndex];
      const seekTo = media.currentTime;
      
      // Only record meaningful seeks (> 1 second difference)
      if (Math.abs(seekTo - seekStartPosition) >= 1.0) {
        recordSeekEvent(track.video_id, seekStartPosition, seekTo, 'progress_bar');
      }
      
      seekStartPosition = null; // Reset
    }
  });
  
  // Function to record seek events
  async function recordSeekEvent(video_id, seek_from, seek_to, source) {
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

  cFull.onclick = () => {
    if (!document.fullscreenElement) {
      wrapper.requestFullscreen?.() || wrapper.webkitRequestFullscreen?.();
    } else {
      document.exitFullscreen?.() || document.webkitExitFullscreen?.();
    }
  };

  // Volume wheel control variables - defined early for scope access
  let volumeWheelTimeout = null;
  let isVolumeWheelActive = false;
  
  // Volume logic
  cMute.onclick = () => {
    media.muted = !media.muted;
    updateMuteIcon();
  };
  cVol.oninput = () => {
    if (isVolumeWheelActive) {
      return;
    }
    media.volume = parseFloat(cVol.value);
    media.muted = media.volume === 0;
    updateMuteIcon();
    saveVolumeToDatabase(media.volume);
  };
  
  // Volume wheel control - adjust volume by 1% with mouse wheel
  
  if (cVol) {
    
    // Function to handle volume wheel adjustment
    function handleVolumeWheel(e) {
      e.preventDefault(); // Prevent page scroll
      e.stopPropagation(); // Stop event bubbling
      
      // Block remote volume commands while user is using wheel
      isVolumeWheelActive = true;
      clearTimeout(volumeWheelTimeout);
      volumeWheelTimeout = setTimeout(() => {
        isVolumeWheelActive = false;
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
    
    // Add wheel event listeners for cross-browser compatibility
    cVol.addEventListener('wheel', handleVolumeWheel, { passive: false });
    cVol.addEventListener('mousewheel', handleVolumeWheel, { passive: false }); // For older browsers
    cVol.addEventListener('DOMMouseScroll', handleVolumeWheel, { passive: false }); // For Firefox
    
    console.log('✅ Volume wheel control setup complete with cross-browser support');
  } else {
    console.error('❌ cVol element not found - wheel control not initialized');
  }
  
  function updateMuteIcon() {
    if (media.muted || media.volume === 0) {
      cMute.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg>';
    } else {
      cMute.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/></svg>';
    }
  }
  
  // Save volume to database with debouncing
  let volumeSaveTimeout = null;
  let lastSavedVolume = null;
  
  async function saveVolumeToDatabase(volume) {
    clearTimeout(volumeSaveTimeout);
    volumeSaveTimeout = setTimeout(async () => {
      try {
        const currentTrack = currentIndex >= 0 && currentIndex < queue.length ? queue[currentIndex] : null;
        const payload = {
          volume: volume,
          volume_from: lastSavedVolume || 1.0,
          video_id: currentTrack ? currentTrack.video_id : 'system',
          position: media.currentTime || null,
          source: 'web'
        };
        
        await fetch('/api/volume/set', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        
        console.log(`💾 Volume saved: ${Math.round((lastSavedVolume || 1.0) * 100)}% → ${Math.round(volume * 100)}%`);
        if (currentTrack) {
          console.log(`🎵 Track: ${currentTrack.name} at ${Math.round(media.currentTime)}s`);
        }
        
        lastSavedVolume = volume;
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
        lastSavedVolume = data.volume; // Set initial saved volume
        console.log(`🔊 Loaded saved volume: ${data.volume_percent}%`);
      } else {
        // Default volume if no saved setting
        media.volume = 1.0;
        cVol.value = 1.0;
        lastSavedVolume = 1.0; // Set default as saved volume
        console.log('🔊 Using default volume: 100%');
      }
    } catch (error) {
      console.warn('⚠️ Failed to load saved volume, using default:', error);
      media.volume = 1.0;
      cVol.value = 1.0;
      lastSavedVolume = 1.0; // Set default as saved volume
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

  // Keyboard shortcuts: ← prev, → next, Space play/pause, Arrow Up/Down for seek
  document.addEventListener('keydown', (e) => {
    switch (e.code) {
      case 'ArrowRight':
        if (e.shiftKey) {
          // Shift + Right = Seek forward 10 seconds
          e.preventDefault();
          performKeyboardSeek(10);
        } else {
          nextTrack();
        }
        break;
      case 'ArrowLeft':
        if (e.shiftKey) {
          // Shift + Left = Seek backward 10 seconds
          e.preventDefault();
          performKeyboardSeek(-10);
        } else {
          prevTrack();
        }
        break;
      case 'ArrowUp':
        e.preventDefault();
        performKeyboardSeek(30); // Seek forward 30 seconds
        break;
      case 'ArrowDown':
        e.preventDefault();
        performKeyboardSeek(-30); // Seek backward 30 seconds
        break;
      case 'Space':
        e.preventDefault();
        togglePlayback();
        break;
    }
  });
  
  // Function to perform keyboard seek
  function performKeyboardSeek(offsetSeconds) {
    if (currentIndex < 0 || currentIndex >= queue.length || !media.duration) return;
    
    const seekFrom = media.currentTime;
    const seekTo = Math.max(0, Math.min(media.duration, seekFrom + offsetSeconds));
    
    if (Math.abs(seekTo - seekFrom) >= 1.0) {
      media.currentTime = seekTo;
      const track = queue[currentIndex];
      recordSeekEvent(track.video_id, seekFrom, seekTo, 'keyboard');
    }
  }

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
      navigator.mediaSession.setActionHandler('previoustrack', () => prevTrack());
      navigator.mediaSession.setActionHandler('nexttrack', () => nextTrack());
      navigator.mediaSession.setActionHandler('play', () => media.play());
      navigator.mediaSession.setActionHandler('pause', () => media.pause());
  }

  // Clicking on the video toggles play/pause
  media.addEventListener('click', togglePlayback);

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
     // Change to filled heart (same icon, but red styling via CSS class)
     cLike.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>';
  };

  cDislike.onclick = ()=>{
     if(currentIndex<0||currentIndex>=queue.length) return;
     const track=queue[currentIndex];
     reportEvent(track.video_id,'dislike', media.currentTime);
     cDislike.classList.add('dislike-active');
     // Change to filled dislike (same icon, but purple styling via CSS class)
     cDislike.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z"></path></svg>';
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

  async function triggerAutoDeleteCheck(track) {
    /**
     * Trigger auto-delete check for finished track if it's from a channel.
     */
    try {
      if (!track || !track.video_id) return;
      
      // Detect if this is channel content
      const detection = detectChannelGroup(track);
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

  // Add null check for streamBtn to prevent errors
  if (streamBtn) {
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
  } else {
    console.warn('🔍 [DEBUG] streamBtn not found, streaming functionality disabled');
  }

  // stop tick when window unload
  window.addEventListener('beforeunload',()=> stopTick());

  // ==============================
  // REMOTE CONTROL SYNCHRONIZATION
  // ==============================
  
  console.log('🔍 [DEBUG] About to start remote control setup...');
  
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
        last_update: Date.now() / 1000,
        player_type: 'virtual',
        player_source: window.location.pathname
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
      console.log('🎮 [Virtual] Polling for remote commands...');
      const response = await fetch('/api/remote/commands');
      console.log('🎮 [Virtual] Poll response status:', response.status);
      if (response.ok) {
        const commands = await response.json();
        console.log('🎮 [Virtual] Poll response data:', commands);
        if (commands && commands.length > 0) {
          console.log('🎮 [Virtual] Received commands:', commands);
        }
        for (const command of commands) {
          await executeRemoteCommand(command);
        }
      } else {
        console.warn('🎮 [Virtual] Poll failed with status:', response.status);
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
          togglePlayback();
          break;
          
        case 'next':
          console.log('🎮 [Remote] Next track');
          nextTrack();
          break;
          
        case 'prev':
          console.log('🎮 [Remote] Previous track');
          prevTrack();
          break;
          
        case 'stop':
          console.log('🎮 [Remote] Stop playback');
          stopPlayback();
          break;
          
        case 'volume':
          if (command.volume !== undefined) {
            if (isVolumeWheelActive) {
              break;
            }
            console.log('🎮 [Remote] Set volume:', Math.round(command.volume * 100) + '%');
            media.volume = command.volume;
            cVol.value = command.volume;
            updateMuteIcon();
            // Note: Volume is already saved by the remote API endpoint
          }
          break;
          
        case 'shuffle':
          console.log('🎮 [Remote] Shuffle playlist - clicking button');
          const shuffleButton = document.getElementById('shuffleBtn');
          if (shuffleButton) {
            console.log('🎮 [Remote] shuffleBtn found, clicking...');
            shuffleButton.click();
          } else {
            console.error('🎮 [Remote] shuffleBtn not found!');
          }
          break;
          
        case 'like':
          console.log('🎮 [Remote] Like track - checking button:', document.getElementById('cLike'));
          const likeButton = document.getElementById('cLike');
          if (likeButton) {
            likeButton.click();
          } else {
            console.error('🎮 [Remote] Like button not found!');
          }
          break;
          
        case 'dislike':
          console.log('🎮 [Remote] Dislike track - checking button:', document.getElementById('cDislike'));
          const dislikeButton = document.getElementById('cDislike');
          if (dislikeButton) {
            dislikeButton.click();
          } else {
            console.error('🎮 [Remote] Dislike button not found!');
          }
          break;
          
        case 'youtube':
          console.log('🎮 [Remote] Open YouTube - checking button:', document.getElementById('cYoutube'));
          const youtubeButton = document.getElementById('cYoutube');
          if (youtubeButton) {
            youtubeButton.click();
          } else {
            console.error('🎮 [Remote] YouTube button not found!');
          }
          break;
          
        case 'fullscreen':
          console.log('🎮 [Remote] Toggle fullscreen - clicking button');
          const fullscreenButton = document.getElementById('cFull');
          if (fullscreenButton) {
            console.log('🎮 [Remote] cFull found, clicking...');
            fullscreenButton.click();
          } else {
            console.error('🎮 [Remote] cFull not found!');
          }
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
  
  // === REMOTE CONTROL INITIALIZATION ===
  console.log('🔧 [Virtual] Starting remote control initialization...');
  
  // Enhanced event listeners for remote sync
  console.log('🔧 [Virtual] Adding event listeners for remote sync...');
  media.addEventListener('play', syncRemoteState);
  media.addEventListener('pause', syncRemoteState);
  media.addEventListener('loadeddata', syncRemoteState);
  media.addEventListener('timeupdate', () => {
    // Sync every 2 seconds during playback
    if (!media.paused && Math.floor(media.currentTime) % 2 === 0) {
      syncRemoteState();
    }
  });
  console.log('✅ [Virtual] Event listeners added successfully');
  
  // Override existing functions to include remote sync
  console.log('🔧 [Virtual] Overriding functions for remote sync...');
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
  console.log('✅ [Virtual] Functions overridden successfully');
  
  // Initial state sync after everything is loaded
  console.log('🔧 [Virtual] Setting up initial sync timer...');
  setTimeout(() => {
    console.log('⏰ [Virtual] Initial sync timer triggered');
    if (currentIndex >= 0) {
      console.log('🎵 [Virtual] Syncing initial state...');
      syncRemoteState();
    }
    // Start periodic sync every 3 seconds
    console.log('🔧 [Virtual] Starting periodic sync interval...');
    setInterval(syncRemoteState, 3000);
  }, 1000);
  
  // Periodic remote command polling (every 1 second)
  console.log('🎮 [Virtual] Setting up command polling interval...');
  const pollInterval = setInterval(pollRemoteCommands, 1000);
  console.log('🎮 [Virtual] Poll interval ID:', pollInterval);
  
  console.log('🎮 Remote control synchronization initialized');
  
  // Function to delete a track
  async function deleteTrack(track, trackIndex) {
    try {
      // Confirm deletion
      const confirmMessage = `Delete track "${track.name.replace(/\s*\[.*?\]$/, '')}" from playlist?\n\nTrack will be moved to trash and can be restored.`;
      if (!confirm(confirmMessage)) {
        return;
      }
      
      console.log(`🗑️ Deleting track: ${track.name} (${track.video_id})`);
      
      // Send delete request to API
      const response = await fetch('/api/delete_track', {
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
        if (trackIndex < currentIndex) {
          currentIndex--;
        } else if (trackIndex === currentIndex) {
          // If we deleted the currently playing track
          if (queue.length > 0) {
            // Play the next track or the first one if we were at the end
            const nextIndex = trackIndex < queue.length ? trackIndex : 0;
            playIndex(nextIndex);
          } else {
            // No tracks left
            media.pause();
            media.src = '';
            currentIndex = -1;
          }
        }
        
        // Update the list display
        renderList();
        
        // Show success message
        showNotification(`✅ Track deleted: ${result.message}`, 'success');
        
      } else {
        console.error('❌ Failed to delete track:', result.error);
        showNotification(`❌ Deletion error: ${result.error}`, 'error');
      }
      
    } catch (error) {
      console.error('❌ Error deleting track:', error);
      showNotification(`❌ Network error: ${error.message}`, 'error');
    }
  }

  // Function to show notifications
  function showNotification(message, type = 'info') {
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

  // ===== GLOBAL TOOLTIP SYSTEM =====
  function setupGlobalTooltip() {
    // Remove existing tooltip if any (like player.js)
    const existingTooltip = document.getElementById('global-tooltip');
    if (existingTooltip) {
      existingTooltip.remove();
    }
    
    // Create global tooltip element (like player.js)
    const tooltip = document.createElement('div');
    tooltip.id = 'global-tooltip';
    tooltip.className = 'custom-tooltip';
    tooltip.style.display = 'none';
    document.body.appendChild(tooltip);
    
    // Add event listeners to all tracks with tooltip data (like player.js)
    const trackItems = listElem.querySelectorAll('li[data-tooltip-html]');
    
    trackItems.forEach(item => {
      item.addEventListener('mouseenter', (e) => {
        const tooltipHTML = item.getAttribute('data-tooltip-html');
        tooltip.innerHTML = tooltipHTML;
        tooltip.style.display = 'block';
        
        // Position tooltip intelligently (copied from player.js)
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

  // Tooltip system will be initialized after rendering tracks in renderList()
  
  // Tooltip system will be initialized in renderList() after tracks are rendered
  
  })(); 