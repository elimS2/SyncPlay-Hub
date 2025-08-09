// Playlist-related utility functions extracted from player-utils.js

// Import dependencies - removed detectChannelGroup as it's now exported from this file

/**
 * Fisher–Yates shuffle (immutable in-place) — extracted from original player-utils.js.
 * @param {Array} array - list to shuffle, modified in place.
 */
export function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
}

/**
 * Smart shuffle based on last playback date
 * Groups tracks by last playback time: 
 * never played > year ago > month ago > week ago > day ago > today
 * @param {Array} list - list of tracks to shuffle
 * @returns {Array} - shuffled list of tracks
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

/**
 * Smart shuffle based on channel groups
 * - Music: Random shuffle with repeat
 * - News: Chronological newest-first (by filename/date)
 * - Education: Sequential oldest-first
 * - Podcasts: Sequential newest-first
 * - Playlists: Smart shuffle (existing logic)
 * @param {Array} tracks - Array of tracks to process
 * @returns {Array} - Processed array of tracks
 */
export function smartChannelShuffle(tracks) {
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
 * Detect channel group from file path — extracted from original player-utils.js.
 * @param {Object} track - track object with relpath property
 * @returns {Object} - { type: 'music'|'news'|'education'|'podcasts'|'playlist', group: string, isChannel: boolean }
 */
export function detectChannelGroup(track) {
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
 * Get playback information for current track mix
 * Analyzes tracks and returns statistics by channel groups
 * @param {Array} tracks - Array of tracks to analyze
 * @returns {Array|null} - Array with group information or null if no tracks
 */
export function getGroupPlaybackInfo(tracks) {
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

/**
 * Trigger auto-delete check for finished track if it's from a channel
 * @param {Object} track - track object
 * @param {Function} detectChannelGroupFn - channel group detection function
 * @param {HTMLAudioElement} media - audio element
 */
export async function triggerAutoDeleteCheck(track, detectChannelGroupFn, media) {
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

/**
 * Load track into player with full metadata and event setup
 * @param {number} idx - track index to load
 * @param {boolean} autoplay - automatically start playback
 * @param {Object} context - execution context
 */
import { updateCurrentTrackTitle } from '../track-title-manager.js';
import { scrollActiveTrackToTop } from '../playlist-scroll.js';

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
    
    // Update current track title display
    updateCurrentTrackTitle(track);
    
    // Update delete button tooltip
    const deleteCurrentBtn = document.getElementById('deleteCurrentBtn');
    if (deleteCurrentBtn && deleteCurrentBtn.updateTooltip) {
        deleteCurrentBtn.updateTooltip();
    }
    
    if('mediaSession' in navigator){
        navigator.mediaSession.metadata = new MediaMetadata({
            title: track.name,
            artist: '',
            album: '',
        });
    }
    castLoad(track);
    renderList();
    // After the list is re-rendered, auto-scroll so the active item is at the top
    scrollActiveTrackToTop({ smooth: false });
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