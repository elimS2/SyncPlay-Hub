/**
 * Track Title Manager - Common module for managing current track title display
 * Shared across all player pages (regular playlist, virtual playlist, etc.)
 */

/**
 * Updates the current track title display
 * @param {Object} track - Track object with name property
 */
export function updateCurrentTrackTitle(track) {
    const currentTrackTitle = document.getElementById('currentTrackTitle');
    const currentTrackName = document.getElementById('currentTrackName');
    
    if (currentTrackTitle && currentTrackName) {
        if (track && track.name) {
            // Remove any metadata tags from the name (e.g., [1080p], [720p], etc.)
            const displayName = track.name.replace(/\s*\[.*?\]$/, '');
            currentTrackName.textContent = displayName;
            currentTrackTitle.classList.add('visible');
        } else {
            currentTrackName.textContent = 'No track selected';
            currentTrackTitle.classList.remove('visible');
        }
        
        // Update width after content change
        setTimeout(() => {
            if (typeof window.updateTrackTitleWidth === 'function') {
                window.updateTrackTitleWidth();
            }
        }, 50);
    }
}

/**
 * Function to update track title and controls width based on video width
 * This function is made globally available for all player pages
 */
export function updateTrackTitleWidth() {
    const videoWrapper = document.getElementById('videoWrapper');
    const currentTrackTitle = document.getElementById('currentTrackTitle');
    const controls = document.querySelector('.controls');
    
    if (videoWrapper && currentTrackTitle && controls) {
        const videoWidth = videoWrapper.offsetWidth;
        const videoLeft = videoWrapper.offsetLeft;
        
        // Set width to match video width and position to match video left
        currentTrackTitle.style.width = videoWidth + 'px';
        currentTrackTitle.style.left = videoLeft + 'px';
        
        controls.style.width = videoWidth + 'px';
        controls.style.left = videoLeft + 'px';
        
        console.log('📏 Updated track title width:', videoWidth + 'px, left:', videoLeft + 'px');
    }
}

/**
 * Initialize track title management system
 * Sets up all necessary event listeners and observers
 */
export function initializeTrackTitleManager() {
    // Update width on window resize
    window.addEventListener('resize', updateTrackTitleWidth);
    
    // Use ResizeObserver to watch for video wrapper and playlist panel size changes
    if (window.ResizeObserver) {
        const videoWrapper = document.getElementById('videoWrapper');
        const playlistPanel = document.getElementById('playlistPanel');
        
        if (videoWrapper) {
            const resizeObserver = new ResizeObserver(() => {
                updateTrackTitleWidth();
            });
            resizeObserver.observe(videoWrapper);
            console.log('👁️ ResizeObserver set up for video wrapper');
        }
        
        if (playlistPanel) {
            const playlistResizeObserver = new ResizeObserver(() => {
                updateTrackTitleWidth();
            });
            playlistResizeObserver.observe(playlistPanel);
            console.log('👁️ ResizeObserver set up for playlist panel');
        }
    }
    
    // Update width when playlist is toggled (backup method)
    const toggleListBtn = document.getElementById('toggleListBtn');
    if (toggleListBtn) {
        const originalToggleListBtn = toggleListBtn.onclick;
        toggleListBtn.onclick = function() {
            if (originalToggleListBtn) {
                originalToggleListBtn.call(this);
            }
            // Update width after playlist toggle animation
            setTimeout(updateTrackTitleWidth, 300);
        };
    }
    
    // Make function globally available for other modules
    window.updateTrackTitleWidth = updateTrackTitleWidth;
    
    // Initial width update
    setTimeout(updateTrackTitleWidth, 100);
    
    console.log('🎵 Track Title Manager initialized');
}

/**
 * Create track title HTML element
 * @returns {HTMLElement} The track title container element
 */
export function createTrackTitleElement() {
    const trackTitleDiv = document.createElement('div');
    trackTitleDiv.id = 'currentTrackTitle';
    
    const trackNameSpan = document.createElement('span');
    trackNameSpan.id = 'currentTrackName';
    trackNameSpan.textContent = 'No track selected';
    
    trackTitleDiv.appendChild(trackNameSpan);
    
    return trackTitleDiv;
}

/**
 * Insert track title element into the page
 * @param {HTMLElement} container - Container element to insert the title into
 * @param {string} position - Position relative to container ('beforebegin', 'afterbegin', 'beforeend', 'afterend')
 */
export function insertTrackTitleElement(container, position = 'beforeend') {
    const trackTitleElement = createTrackTitleElement();
    container.insertAdjacentElement(position, trackTitleElement);
    return trackTitleElement;
} 