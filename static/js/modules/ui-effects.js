// UI effects and interface update functions extracted from player-utils.js

// Import dependencies
import { formatFileSize } from './dom-utils.js';
import { getCurrentLayoutMode, LAYOUT_MODES } from './playlist-layout-manager.js';

/**
 * Update playback speed display
 * @param {number} currentSpeedIndex - current speed index
 * @param {Array} speedOptions - array of available speeds
 * @param {HTMLElement} speedLabel - element to display speed
 * @param {HTMLElement} cSpeed - speed control button
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
 * Show controls in fullscreen mode with auto-hide after 3 seconds
 * Uses global variables: customControls, controlBar, fsTimer
 * @param {Object} context - context with customControls, controlBar, fsTimer
 */
export function showFsControls(context) {
    const { customControls, controlBar, fsTimer } = context || window;
    
    if(!document.fullscreenElement) return;
    customControls.classList.remove('hidden');
    controlBar.classList.remove('hidden');
    clearTimeout(fsTimer);
    
    // Update fsTimer in context or globally
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
 * Update visibility of elements when entering/exiting fullscreen mode
 * Manages list visibility and sets up mouse event handlers
 * @param {Object} context - context with listElem, customControls, controlBar, wrapper, fsTimer
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
 * Show notification to user
 * @param {string} message - notification text
 * @param {string} type - notification type ('info', 'success', 'error')
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
 * Create HTML for track tooltip with all metadata and statistics
 * @param {Object} track - track data
 * @returns {string} HTML content for tooltip
 */
export function createTrackTooltipHTML(track) {
  let tooltipHTML = '';
  // Precompute media property rows for consistent ordering and grouping
  let durationRowHTML = '';
  let fileSizeRowHTML = '';
  let bitrateRowHTML = '';
  let resolutionRowHTML = '';
  let filetypeRowHTML = '';
  
  // Add channel handle (@channelname) info - FIRST ITEM
  if (track.youtube_channel_handle) {
    tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg><strong>Channel:</strong> ${track.youtube_channel_handle}</div>`;
  }
  
  // Add YouTube ID info
  if (track.video_id) {
    tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 19a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"></path><path d="M8 9h8"></path><path d="M8 15h6"></path></svg><strong>YouTube ID:</strong> ${track.video_id}</div>`;
  }
  
  // Add YouTube publish date info
  if (track.youtube_timestamp || track.youtube_release_timestamp || track.youtube_release_year) {
    let publishDate = 'Unknown';
    
    if (track.youtube_timestamp) {
      const date = new Date(track.youtube_timestamp * 1000);
      publishDate = date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    } else if (track.youtube_release_timestamp) {
      const date = new Date(track.youtube_release_timestamp * 1000);
      publishDate = date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    } else if (track.youtube_release_year) {
      publishDate = track.youtube_release_year;
    }
    
    tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg><strong>Publish Date:</strong> ${publishDate}</div>`;
  } else {
    tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg><strong>Publish Date:</strong> Unknown</div>`;
  }
  
  // Add YouTube view count info
  if (track.youtube_view_count !== undefined && track.youtube_view_count !== null) {
    const viewCount = Number(track.youtube_view_count).toLocaleString();
    tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg><strong>YouTube Views:</strong> ${viewCount}</div>`;
  }
  
  // Add metadata sync date info
  if (track.youtube_metadata_updated) {
    try {
      const syncDate = new Date(track.youtube_metadata_updated);
      const syncFormatted = syncDate.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
      tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"></path></svg><strong>Metadata Synced:</strong> ${syncFormatted}</div>`;
    } catch (e) {
      tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"></path></svg><strong>Metadata Synced:</strong> Unknown</div>`;
    }
  }
  
  // Prepare duration row (do not append yet)
  if (track.youtube_duration_string) {
    durationRowHTML = `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg><strong>Duration:</strong> ${track.youtube_duration_string}</div>`;
  } else if (track.youtube_duration) {
    const duration = Math.floor(track.youtube_duration);
    const minutes = Math.floor(duration / 60);
    const seconds = duration % 60;
    const durationStr = `${minutes}:${seconds.toString().padStart(2, '0')}`;
    durationRowHTML = `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg><strong>Duration:</strong> ${durationStr}</div>`;
  } else {
    durationRowHTML = `<div class=\"tooltip-row\"><svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><circle cx=\"12\" cy=\"12\" r=\"10\"></circle><polyline points=\"12,6 12,12 16,14\"></polyline></svg><strong>Duration:</strong> -</div>`;
  }

  // Prepare file size row
  if (track.size_bytes) {
    const fileSize = formatFileSize(track.size_bytes);
    fileSizeRowHTML = `<div class=\"tooltip-row\"><svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z\"></path><polyline points=\"14,2 14,8 20,8\"></polyline></svg><strong>File Size:</strong> ${fileSize}</div>`;
  } else {
    fileSizeRowHTML = `<div class=\"tooltip-row\"><svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z\"></path><polyline points=\"14,2 14,8 20,8\"></polyline></svg><strong>File Size:</strong> -</div>`;
  }

  // Prepare bitrate row (kbps)
  if (typeof track.bitrate === 'number' && track.bitrate > 0) {
    const kbps = Math.round(track.bitrate / 1000);
    bitrateRowHTML = `<div class=\"tooltip-row\"><svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><polyline points=\"3,12 7,12 9,19 13,5 15,12 21,12\"></polyline></svg><strong>Bitrate:</strong> ${kbps} kbps</div>`;
  } else {
    bitrateRowHTML = `<div class=\"tooltip-row\"><svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><polyline points=\"3,12 7,12 9,19 13,5 15,12 21,12\"></polyline></svg><strong>Bitrate:</strong> -</div>`;
  }

  // Prepare resolution row
  if (track.resolution) {
    resolutionRowHTML = `<div class=\"tooltip-row\"><svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><rect x=\"3\" y=\"6\" width=\"18\" height=\"12\" rx=\"2\"></rect></svg><strong>Resolution:</strong> ${track.resolution}</div>`;
  } else {
    resolutionRowHTML = `<div class=\"tooltip-row\"><svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><rect x=\"3\" y=\"6\" width=\"18\" height=\"12\" rx=\"2\"></rect></svg><strong>Resolution:</strong> -</div>`;
  }

  // Prepare file type row
  if (track.filetype) {
    filetypeRowHTML = `<div class=\"tooltip-row\"><svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z\"></path><polyline points=\"14,2 14,8 20,8\"></polyline></svg><strong>Type:</strong> ${track.filetype}</div>`;
  } else {
    filetypeRowHTML = `<div class=\"tooltip-row\"><svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z\"></path><polyline points=\"14,2 14,8 20,8\"></polyline></svg><strong>Type:</strong> -</div>`;
  }
  
  // Add last play date info
  if (track.last_play) {
    try {
      const lastPlayDate = new Date(track.last_play.replace(' ', 'T') + 'Z');
      const lastPlayFormatted = lastPlayDate.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
      tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg><strong>Last Played:</strong> ${lastPlayFormatted}</div>`;
    } catch (e) {
      tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg><strong>Last Played:</strong> Never</div>`;
    }
  } else {
    tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12,6 12,12 16,14"></polyline></svg><strong>Last Played:</strong> Never</div>`;
  }

  // Add media properties section (grouped)
  tooltipHTML += `<div class="tooltip-section"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="6" width="18" height="12" rx="2"></rect></svg><strong>Media Properties:</strong></div>`;
  tooltipHTML += durationRowHTML;
  tooltipHTML += fileSizeRowHTML;
  tooltipHTML += bitrateRowHTML;
  tooltipHTML += resolutionRowHTML;
  tooltipHTML += filetypeRowHTML;

  // Add playback statistics
  tooltipHTML += `<div class="tooltip-section"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="20" x2="12" y2="10"></line><line x1="18" y1="20" x2="18" y2="4"></line><line x1="6" y1="20" x2="6" y2="16"></line></svg><strong>Playback Statistics:</strong></div>`;
  tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5,3 19,12 5,21"></polygon></svg>Total Plays: ${track.play_starts || 0}</div>`;
  tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"></polyline></svg>Completed Plays: ${track.play_finishes || 0}</div>`;
  tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5,4 15,12 5,20"></polygon><line x1="19" y1="5" x2="19" y2="19"></line></svg>Next Button Clicks: ${track.play_nexts || 0}</div>`;
  const netLikes = (track.play_likes || 0) - (track.play_dislikes || 0);
  tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>Likes: ${track.play_likes || 0}</div>`;
  tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9b59b6" stroke-width="2"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3z"></path></svg>Dislikes: ${track.play_dislikes || 0}</div>`;
  tooltipHTML += `<div class="tooltip-row"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4CAF50" stroke-width="2"><path d="M9 12l2 2 4-4"></path><circle cx="12" cy="12" r="10"></circle></svg><strong>Net Likes: ${netLikes}</strong></div>`;
  
  return tooltipHTML;
}

/**
 * Setup global tooltip system for track elements
 * Creates a single tooltip element and adds handlers for all tracks with data-tooltip-html
 * @param {HTMLElement} listElem - list element to search for tooltip elements
 */
export function setupGlobalTooltip(listElem) {
    const TOOLTIP_VERTICAL_SPACING = 4;
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
            const layoutMode = getCurrentLayoutMode ? getCurrentLayoutMode() : null;
            const isUnderVideo = layoutMode === LAYOUT_MODES.UNDER_VIDEO;

            if (isUnderVideo) {
                // Prefer showing the tooltip below the hovered row
                top = rect.top + rect.height + TOOLTIP_VERTICAL_SPACING;
                // If it overflows bottom, place it above the row
                if (top + tooltipRect.height > windowHeight - 10) {
                    top = rect.top - tooltipRect.height - TOOLTIP_VERTICAL_SPACING;
                }
            } else {
                // Default behavior for side-by-side and other modes
                top = rect.top;
            }
            
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