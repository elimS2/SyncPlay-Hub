// Toast notification system for SyncPlay-Hub Remote
// Extracted from remote.js for better modularity

/**
 * Generic toast notification function
 * @param {string} message - Message to display
 * @param {Object} options - Toast configuration options
 */
function showToast(message, options = {}) {
  const defaults = {
    id: 'genericToast',
    position: 'center', // 'top', 'center', 'bottom'
    duration: 3000,
    backgroundColor: 'rgba(0, 0, 0, 0.9)',
    color: 'white',
    fontSize: '14px',
    fontWeight: '500',
    padding: '15px 25px',
    borderRadius: '12px',
    maxWidth: '80vw',
    zIndex: 10000
  };
  
  const config = { ...defaults, ...options };
  
  // Remove existing toast with same ID
  const existingToast = document.getElementById(config.id);
  if (existingToast) {
    existingToast.remove();
  }
  
  // Create toast element
  const toast = document.createElement('div');
  toast.id = config.id;
  
  // Set position
  let positionStyle = '';
  switch (config.position) {
    case 'top':
      positionStyle = 'top: 20px; left: 50%; transform: translateX(-50%);';
      break;
    case 'bottom':
      positionStyle = 'bottom: 20px; left: 50%; transform: translateX(-50%);';
      break;
    case 'center':
    default:
      positionStyle = 'top: 50%; left: 50%; transform: translate(-50%, -50%);';
      break;
  }
  
  toast.style.cssText = `
    position: fixed;
    ${positionStyle}
    background: ${config.backgroundColor};
    color: ${config.color};
    padding: ${config.padding};
    border-radius: ${config.borderRadius};
    font-size: ${config.fontSize};
    font-weight: ${config.fontWeight};
    z-index: ${config.zIndex};
    pointer-events: none;
    backdrop-filter: blur(10px);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.1);
    max-width: ${config.maxWidth};
    text-align: center;
  `;
  
  toast.textContent = message;
  document.body.appendChild(toast);
  
  // Auto remove after specified duration
  setTimeout(() => {
    if (toast.parentNode) {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }
  }, config.duration);
}

/**
 * Show volume toast notification
 * @param {number} volume - Volume level (0-100)
 */
function showVolumeToast(volume) {
  // Remove existing toast
  const existingToast = document.getElementById('volumeToast');
  if (existingToast) {
    existingToast.remove();
  }
  
  // Create volume toast
  const toast = document.createElement('div');
  toast.id = 'volumeToast';
  toast.style.cssText = `
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: rgba(0, 0, 0, 0.8);
    color: white;
    padding: 20px 30px;
    border-radius: 15px;
    font-size: 18px;
    font-weight: bold;
    z-index: 10000;
    pointer-events: none;
    backdrop-filter: blur(10px);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
  `;
  
  const volumeIcon = volume === 0 
    ? `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
         <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
         <line x1="23" y1="9" x2="17" y2="15"></line>
         <line x1="17" y1="9" x2="23" y2="15"></line>
       </svg>`
    : volume < 30 
      ? `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
         </svg>`
      : volume < 70 
        ? `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
             <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
             <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
           </svg>`
        : `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
             <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
             <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
           </svg>`;
  toast.innerHTML = `${volumeIcon} ${volume}%`;
  
  document.body.appendChild(toast);
  
  // Auto remove after 1.5 seconds
  setTimeout(() => {
    if (toast.parentNode) {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }
  }, 1500);
}

/**
 * Show keep awake toast notification
 * @param {string} message - Message to display
 */
function showKeepAwakeToast(message) {
  // Remove existing toast
  const existingToast = document.getElementById('keepAwakeToast');
  if (existingToast) {
    existingToast.remove();
  }
  
  // Create keep awake toast
  const toast = document.createElement('div');
  toast.id = 'keepAwakeToast';
  toast.style.cssText = `
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: rgba(0, 0, 0, 0.9);
    color: white;
    padding: 15px 25px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 500;
    z-index: 10000;
    pointer-events: none;
    backdrop-filter: blur(10px);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.1);
    max-width: 80vw;
    text-align: center;
  `;
  
  toast.textContent = message;
  document.body.appendChild(toast);
  
  // Auto remove after 3 seconds for longer messages
  setTimeout(() => {
    if (toast.parentNode) {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }
  }, 3000);
}

// Export functions for use by other modules
if (typeof module !== 'undefined' && module.exports) {
  // Node.js environment
  module.exports = {
    showToast,
    showVolumeToast,
    showKeepAwakeToast
  };
} else {
  // Browser environment - attach to window object
  window.ToastNotifications = {
    showToast,
    showVolumeToast,
    showKeepAwakeToast
  };
} 