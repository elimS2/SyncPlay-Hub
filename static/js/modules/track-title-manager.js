/**
 * Track Title Manager - Common module for managing current track title display
 * Shared across all player pages (regular playlist, virtual playlist, etc.)
 */

/**
 * Generate segments from track name using all helper functions
 * @param {string} trackName - Full track name to process
 * @returns {Array} Array of segment objects ready for display
 */
function generateSegments(trackName) {
    if (!trackName) return [];
    
    // Remove metadata tags from the end (e.g., [1080p], [720p], etc.)
    const cleanName = trackName.replace(/\s*\[.*?\]$/, '');
    
    // Find all separators in the text
    const separators = findSeparators(cleanName);
    
    // Split text by separators and generate segments
    const [segments, debugLog] = splitBySeparators(cleanName, separators);
    
    return segments;
}

/**
 * Split text at separator boundaries while preserving spacing
 * @param {string} text - Text to split
 * @param {Array} separators - Array of separator objects from findSeparators()
 * @returns {Array} Array of text segments with separators included
 */
function splitBySeparators(text, separators) {
    console.log('🔍 [DEBUG] splitBySeparators called with:', { text, separators });
    
    if (separators.length === 0) {
        console.log('🔍 [DEBUG] No separators found, returning single segment');
        return [[{
            text: text,
            originalText: text, // Keep original for reconstruction
            searchQuery: text.trim(),
            isClickable: true
        }], ''];
    }
    
    const segments = [];
    let currentIndex = 0;
    
    for (let i = 0; i < separators.length; i++) {
        const separator = separators[i];
        console.log(`🔍 [DEBUG] Processing separator ${i}:`, {
            separator: separator.separator,
            index: separator.index,
            endIndex: separator.endIndex,
            currentIndex
        });
        
        // Get text before this separator
        const beforeSeparator = text.substring(currentIndex, separator.index);
        console.log(`🔍 [DEBUG] Text before separator: "${beforeSeparator}" (${currentIndex} to ${separator.index})`);
        
        if (beforeSeparator.trim()) {
            segments.push({
                text: beforeSeparator,
                originalText: beforeSeparator, // Keep original for reconstruction
                searchQuery: cleanSearchQuery(beforeSeparator),
                isClickable: true
            });
            console.log(`🔍 [DEBUG] Added segment: "${beforeSeparator}"`);
        }
        
        // Get text from separator to next separator (or end)
        const nextSeparator = separators[i + 1];
        const endIndex = nextSeparator ? nextSeparator.index : text.length;
        const segmentText = text.substring(separator.index, endIndex);
        
        console.log(`🔍 [DEBUG] Segment text: "${segmentText}" (${separator.index} to ${endIndex})`);
        
                        if (segmentText.trim()) {
                    const searchQuery = cleanSearchQuery(segmentText);
                    // Only add segment if it has a meaningful search query
                    if (searchQuery.trim()) {
                        // Split the segment into separator and content
                        const separatorPart = separator.separator;
                        const contentPart = segmentText.substring(separator.separator.length);
                        
                        // Add separator as non-clickable segment
                        if (separatorPart.trim()) {
                            // Clean separator boundaries - remove only spaces, keep brackets
                            const cleanSeparator = separatorPart
                                .replace(/^\s+/, '') // Remove leading spaces only
                                .replace(/\s+$/, ''); // Remove trailing spaces only
                            
                            if (cleanSeparator.trim()) {
                                segments.push({
                                    text: separatorPart, // Use original with spaces for display
                                    originalText: separatorPart, // Keep original for reconstruction
                                    searchQuery: null,
                                    isClickable: false
                                });
                                console.log(`🔍 [DEBUG] Added separator segment: "${separatorPart}" (non-clickable)`);
                            } else {
                                // If separator becomes empty after cleaning, use original
                                segments.push({
                                    text: separatorPart,
                                    originalText: separatorPart,
                                    searchQuery: null,
                                    isClickable: false
                                });
                                console.log(`🔍 [DEBUG] Added original separator segment: "${separatorPart}" (non-clickable)`);
                            }
                        }
                        
                        // Add content as clickable segment
                        if (contentPart.trim()) {
                            // Clean content boundaries - remove leading/trailing spaces and brackets
                            const cleanContent = contentPart
                                .replace(/^[\s()]+/, '') // Remove leading spaces and brackets
                                .replace(/[\s()]+$/, ''); // Remove trailing spaces and brackets
                            
                            if (cleanContent.trim()) {
                                segments.push({
                                    text: contentPart, // Use original content with all spaces for display
                                    originalText: contentPart, // Keep original for reconstruction
                                    searchQuery: searchQuery,
                                    isClickable: true
                                });
                                console.log(`🔍 [DEBUG] Added content segment: "${contentPart}" with query: "${searchQuery}"`);
                            }
                        }
                    } else {
                        // If this segment would be empty, check if it's just a separator
                        if (segmentText.trim() === separator.separator.trim()) {
                            // This is just a separator, add it as a separator segment
                            const cleanSeparator = separator.separator
                                .replace(/^\s+/, '') // Remove leading spaces only
                                .replace(/\s+$/, ''); // Remove trailing spaces only
                            
                            if (cleanSeparator.trim()) {
                                segments.push({
                                    text: segmentText, // Use original with spaces for display
                                    originalText: segmentText, // Use full segmentText for reconstruction
                                    searchQuery: null,
                                    isClickable: false
                                });
                                console.log(`🔍 [DEBUG] Added separator-only segment: "${segmentText}" (non-clickable)`);
                            }
                        } else {
                            // If this segment would be empty, append it to the previous segment
                            if (segments.length > 0) {
                                const lastSegment = segments[segments.length - 1];
                                lastSegment.text += segmentText;
                                lastSegment.originalText += segmentText;
                                console.log(`🔍 [DEBUG] Appended empty segment "${segmentText}" to previous segment: "${lastSegment.text}"`);
                            } else {
                                console.log(`🔍 [DEBUG] Skipped empty segment: "${segmentText}" (cleaned to: "${searchQuery}") - no previous segment to append to`);
                            }
                        }
                    }
                } else {
                    // Handle case where segmentText is just whitespace or empty
                    if (separator.separator.trim()) {
                        // Clean separator boundaries - remove only spaces, keep brackets
                        const cleanSeparator = separator.separator
                            .replace(/^\s+/, '') // Remove leading spaces only
                            .replace(/\s+$/, ''); // Remove trailing spaces only
                        
                        if (cleanSeparator.trim()) {
                            segments.push({
                                text: segmentText, // Use original with spaces for display
                                originalText: segmentText, // Use full segmentText for reconstruction
                                searchQuery: null,
                                isClickable: false
                            });
                            console.log(`🔍 [DEBUG] Added separator-only segment: "${segmentText}" (non-clickable)`);
                        } else {
                            // If separator becomes empty after cleaning, use original
                            segments.push({
                                text: segmentText, // Use original with spaces for display
                                originalText: segmentText, // Use full segmentText for reconstruction
                                searchQuery: null,
                                isClickable: false
                            });
                            console.log(`🔍 [DEBUG] Added original separator-only segment: "${segmentText}" (non-clickable)`);
                        }
                    }
                }
        
        // Move to the end of current segment
        currentIndex = endIndex;
        console.log(`🔍 [DEBUG] Updated currentIndex to: ${currentIndex}`);
    }
    
    console.log('🔍 [DEBUG] Final segments:', segments);
    return [segments, ''];
}

/**
 * Find all separator positions in the text
 * @param {string} text - Text to analyze
 * @returns {Array} Array of separator objects with position and type
 */
function findSeparators(text) {
    const separators = [];
    
    // Find individual separators (dash, vertical bar)
    const individualSeparators = /\s*[-–—|]\s*/g;
    let match;
    
    while ((match = individualSeparators.exec(text)) !== null) {
        separators.push({
            separator: match[0],
            index: match.index,
            endIndex: match.index + match[0].length,
            type: 'individual'
        });
    }
    
    // Find parentheses as separate separators
    const parenthesesRegex = /[()]/g;
    while ((match = parenthesesRegex.exec(text)) !== null) {
        separators.push({
            separator: match[0],
            index: match.index,
            endIndex: match.index + match[0].length,
            type: 'parenthesis'
        });
    }
    
    // Sort separators by position
    separators.sort((a, b) => a.index - b.index);
    
    // Remove overlapping separators (keep the first one)
    const filteredSeparators = [];
    for (let i = 0; i < separators.length; i++) {
        const current = separators[i];
        const overlaps = filteredSeparators.some(existing => 
            (current.index >= existing.index && current.index < existing.endIndex) ||
            (existing.index >= current.index && existing.index < current.endIndex)
        );
        
        if (!overlaps) {
            filteredSeparators.push(current);
        }
    }
    
    return filteredSeparators;
}

/**
 * Clean search query by removing separators and extra spaces
 * @param {string} text - Text to clean
 * @returns {string} Cleaned search query
 */
function cleanSearchQuery(text) {
    return text
        .replace(/^[-–—()|\s]+/, '') // Remove leading separators and spaces
        .replace(/[-–—()|\s]+$/, '') // Remove trailing separators and spaces
        .replace(/\s+/g, ' ') // Replace multiple spaces with single space
        .trim();
}

/**
 * Parse track name into searchable segments
 * @param {string} trackName - Full track name
 * @returns {Array} Array of objects with text and search query
 */
function parseTrackName(trackName) {
    // Use the new simplified approach with helper functions
    return generateSegments(trackName);
}

/**
 * Get hover color for a segment based on its index
 * @param {number} index - Segment index
 * @returns {string} CSS color value
 */
function getHoverColor(index) {
    const colors = [
        '#61dafb', // Light blue
        '#ff6b6b', // Red
        '#4ecdc4', // Teal
        '#45b7d1', // Blue
        '#96ceb4', // Green
        '#feca57', // Yellow
        '#ff9ff3', // Pink
        '#54a0ff', // Blue
        '#5f27cd', // Purple
        '#00d2d3', // Cyan
        '#ff9f43', // Orange
        '#10ac84', // Emerald
        '#ee5a24', // Red-orange
        '#575fcf', // Indigo
        '#0abde3'  // Light blue
    ];
    
    return colors[index % colors.length];
}

/**
 * Updates the current track title display
 * @param {Object} track - Track object with name property
 */
export function updateCurrentTrackTitle(track) {
    const currentTrackTitle = document.getElementById('currentTrackTitle');
    const currentTrackName = document.getElementById('currentTrackName');
    
    if (currentTrackTitle && currentTrackName) {
        if (track && track.name) {
            console.log('🔍 [PRODUCTION] Processing track:', track.name);
            
            // Parse track name into segments
            const segments = parseTrackName(track.name);
            console.log('🔍 [PRODUCTION] Generated segments:', segments);
            
            // Clear existing content
            currentTrackName.innerHTML = '';
            
            // Create elements for each segment
            segments.forEach((segment, index) => {
                console.log(`🔍 [UI] Creating segment ${index}:`, {
                    text: segment.text,
                    isClickable: segment.isClickable,
                    searchQuery: segment.searchQuery
                });
                
                if (segment.isClickable) {
                    // Create clickable link for clickable segments
                    const link = document.createElement('a');
                    link.href = `/tracks?search=${encodeURIComponent(segment.searchQuery)}`;
                    link.target = '_blank';
                    link.textContent = segment.text;
                    link.className = 'track-name-link';
                    link.title = `Search for "${segment.searchQuery}"`;
                    
                    // Add custom hover color
                    const hoverColor = getHoverColor(index);
                    link.style.setProperty('--hover-color', hoverColor);
                    
                    currentTrackName.appendChild(link);
                } else {
                    // Create plain text span for non-clickable segments (separators)
                    const span = document.createElement('span');
                    span.textContent = segment.text;
                    currentTrackName.appendChild(span);
                }
            });
            
            // Debug final HTML
            console.log('🔍 [UI] Final HTML content:', currentTrackName.innerHTML);
            console.log('🔍 [UI] Final text content:', currentTrackName.textContent);
            
            // Add hover event listeners for group highlighting
            const clickableLinks = currentTrackName.querySelectorAll('.track-name-link');
            clickableLinks.forEach((link, index) => {
                const hoverColor = getHoverColor(index);
                
                link.addEventListener('mouseenter', () => {
                    // Highlight all segments with their respective colors
                    clickableLinks.forEach((otherLink, otherIndex) => {
                        const otherColor = getHoverColor(otherIndex);
                        otherLink.style.color = otherColor;
                    });
                });
                
                link.addEventListener('mouseleave', () => {
                    // Reset all segments to default color
                    clickableLinks.forEach((otherLink) => {
                        otherLink.style.color = '';
                    });
                });
            });
            
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
    
    // Update delete button tooltip with current track info
    const deleteCurrentBtn = document.getElementById('deleteCurrentBtn');
    if (deleteCurrentBtn && deleteCurrentBtn.updateTooltip) {
        deleteCurrentBtn.updateTooltip();
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
    
    // Update width when playlist layout changes (backup method)
    const toggleLayoutBtn = document.getElementById('toggleLayoutBtn');
    if (toggleLayoutBtn) {
        const originalToggleLayoutBtn = toggleLayoutBtn.onclick;
        toggleLayoutBtn.onclick = function() {
            if (originalToggleLayoutBtn) {
                originalToggleLayoutBtn.call(this);
            }
            // Update width after playlist layout change animation
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