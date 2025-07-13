// Keep Awake system for SyncPlay-Hub Remote
// Extracted from remote.js for better modularity

// Wake Lock state management
let wakeLock = null;
let wakeLockSupported = false;
let keepAwakeMethod = 'none';
let keepAwakeActive = false;
let keepAwakeInterval = null;
let hiddenVideo = null;
let webRTCConnection = null;

// Import toast notifications (use global reference)
function getShowKeepAwakeToast() {
  return window.showKeepAwakeToast || (window.ToastNotifications && window.ToastNotifications.showKeepAwakeToast) || null;
}

function initCSSKeepAwake() {
  // Create a continuously animating invisible element
  const animationElement = document.createElement('div');
  animationElement.id = 'cssKeepAwake';
  animationElement.style.cssText = `
    position: fixed;
    top: -3px;
    left: -3px;
    width: 1px;
    height: 1px;
    opacity: 0.001;
    pointer-events: none;
    z-index: -1000;
    animation: keepAwakeAnimation 2s infinite linear;
  `;
  
  // Create CSS animation keyframes
  const style = document.createElement('style');
  style.textContent = `
    @keyframes keepAwakeAnimation {
      0% { transform: translateX(0px) rotate(0deg); }
      25% { transform: translateX(0.1px) rotate(90deg); }
      50% { transform: translateX(0px) rotate(180deg); }
      75% { transform: translateX(-0.1px) rotate(270deg); }
      100% { transform: translateX(0px) rotate(360deg); }
    }
  `;
  
  document.head.appendChild(style);
  document.body.appendChild(animationElement);
  
  console.log('📱 CSS animation keep awake initialized');
}

function stopKeepAwake() {
  // Stop wake lock
  if (wakeLock) {
    wakeLock.release();
    wakeLock = null;
  }
  
  // Stop video
  if (hiddenVideo) {
    hiddenVideo.pause();
    hiddenVideo.remove();
    hiddenVideo = null;
  }
  
  // Stop periodic method
  if (keepAwakeInterval) {
    clearInterval(keepAwakeInterval);
    keepAwakeInterval = null;
  }
  
  // Stop CSS animation
  const cssKeepAwakeElement = document.getElementById('cssKeepAwake');
  if (cssKeepAwakeElement) {
    cssKeepAwakeElement.remove();
  }
  
  // Stop WebRTC connection
  if (webRTCConnection) {
    webRTCConnection.close();
    webRTCConnection = null;
  }
  
  // Exit fullscreen if active
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {});
  }
  
  keepAwakeActive = false;
  console.log('📱 Keep awake stopped');
  updateKeepAwakeStatus();
}

function initWebRTCKeepAwake() {
  try {
    // Close existing WebRTC connection if any
    if (webRTCConnection) {
      webRTCConnection.close();
    }
    
    // Create a fake WebRTC connection to keep browser active
    const configuration = {
      iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
    };
    
    webRTCConnection = new RTCPeerConnection(configuration);
    
    // Create a fake video track from canvas
    const canvas = document.createElement('canvas');
    canvas.width = 1;
    canvas.height = 1;
    const ctx = canvas.getContext('2d');
    
    // Create minimal animation on canvas
    let frame = 0;
    const animateWebRTCCanvas = () => {
      ctx.fillStyle = frame % 2 === 0 ? '#000000' : '#000001';
      ctx.fillRect(0, 0, 1, 1);
      frame++;
      setTimeout(animateWebRTCCanvas, 5000); // Very slow animation
    };
    animateWebRTCCanvas();
    
    // Get stream from canvas
    const stream = canvas.captureStream(0.2); // Very low frame rate
    
    // Add tracks to WebRTC connection
    stream.getTracks().forEach(track => {
      webRTCConnection.addTrack(track, stream);
    });
    
    // Create data channel for additional activity
    const dataChannel = webRTCConnection.createDataChannel('keepAwake', {
      ordered: false,
      maxRetransmits: 0
    });
    
    // Send periodic data
    const sendKeepAliveData = () => {
      if (dataChannel.readyState === 'open') {
        dataChannel.send('ping');
      }
      setTimeout(sendKeepAliveData, 30000); // Every 30 seconds
    };
    
    dataChannel.addEventListener('open', () => {
      console.log('📱 WebRTC keep awake data channel opened');
      sendKeepAliveData();
    });
    
    // Create offer but don't actually connect anywhere
    webRTCConnection.createOffer().then(offer => {
      return webRTCConnection.setLocalDescription(offer);
    }).catch(() => {
      // Ignore errors, this is just for keep awake
    });
    
    console.log('📱 WebRTC keep awake initialized');
    return true;
    
  } catch (error) {
    console.log('📱 WebRTC keep awake failed:', error);
    return false;
  }
}

function initKeepAwakeHandlers() {
  // Request keep awake when page becomes visible
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && !keepAwakeActive) {
      console.log('📱 Page became visible, requesting keep awake...');
      setTimeout(requestWakeLock, 500);
    }
  });
  
  // Re-request keep awake on focus
  window.addEventListener('focus', () => {
    if (!keepAwakeActive) {
      console.log('📱 Window focused, requesting keep awake...');
      setTimeout(requestWakeLock, 500);
    }
  });
  
  // Stop keep awake when page is hidden (save battery)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      console.log('📱 Page hidden, stopping keep awake...');
      stopKeepAwake();
    }
  });
  
  // Initial keep awake request
  console.log('📱 Initializing keep awake system...');
  requestWakeLock();
}

function tryPeriodicKeepAwake() {
  try {
    // Clear existing interval
    if (keepAwakeInterval) {
      clearInterval(keepAwakeInterval);
    }
    
    console.log('📱 Starting aggressive periodic keep awake method');
    
    // Multiple types of periodic events to prevent sleep
    keepAwakeInterval = setInterval(() => {
      try {
        // Method 1: Tiny canvas animation
        const canvas = document.createElement('canvas');
        canvas.width = 1;
        canvas.height = 1;
        canvas.style.cssText = `
          position: fixed;
          top: -2px;
          left: -2px;
          opacity: 0.01;
          pointer-events: none;
          z-index: -1000;
        `;
        document.body.appendChild(canvas);
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, 1, 1);
        setTimeout(() => canvas.remove(), 100);
        
        // Method 2: Focus shift
        const hiddenInput = document.createElement('input');
        hiddenInput.style.cssText = `
          position: fixed;
          top: -10px;
          left: -10px;
          width: 1px;
          height: 1px;
          opacity: 0;
          pointer-events: none;
          z-index: -1000;
        `;
        document.body.appendChild(hiddenInput);
        hiddenInput.focus();
        hiddenInput.blur();
        setTimeout(() => hiddenInput.remove(), 100);
        
        // Method 3: Vibration API (if available)
        if ('vibrate' in navigator) {
          navigator.vibrate(1);
        }
        
        // Method 4: Document interaction
        document.dispatchEvent(new Event('touchstart', { bubbles: true }));
        document.dispatchEvent(new Event('mousemove', { bubbles: true }));
        
        // Method 5: Window animation frame
        requestAnimationFrame(() => {
          const dummy = document.createElement('div');
          dummy.style.transform = 'translateX(0.1px)';
          document.body.appendChild(dummy);
          setTimeout(() => dummy.remove(), 10);
        });
        
        console.log('📱 Keep awake ping sent');
        
      } catch (error) {
        console.log('📱 Keep awake ping error:', error);
      }
      
    }, 4000); // Every 4 seconds - very frequent
    
    // Additional audio context method
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      
      gainNode.gain.value = 0; // Silent
      oscillator.frequency.value = 20000; // Very high frequency
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.001); // Very short
      
      // Keep audio context alive
      setInterval(() => {
        if (audioContext.state === 'suspended') {
          audioContext.resume().catch(() => {});
        }
      }, 10000);
      
      console.log('📱 Audio context keep awake initialized');
    } catch (error) {
      console.log('📱 Audio context method failed:', error);
    }
    
    return true;
  } catch (error) {
    console.log('📱 Periodic keep awake method failed:', error);
    return false;
  }
}

async function requestWakeLock() {
  // Try Wake Lock API first (modern browsers, HTTPS required)
  if ('wakeLock' in navigator && location.protocol === 'https:') {
    try {
      if (wakeLock) {
        wakeLock.release();
      }
      
      wakeLock = await navigator.wakeLock.request('screen');
      keepAwakeMethod = 'wakeLock';
      keepAwakeActive = true;
      console.log('📱 Wake Lock API: Screen awake mode activated');
      updateKeepAwakeStatus();
      
      wakeLock.addEventListener('release', () => {
        console.log('📱 Wake Lock API: Screen awake mode deactivated');
        wakeLock = null;
        keepAwakeActive = false;
        updateKeepAwakeStatus();
        
        // Auto re-request wake lock after a short delay
        setTimeout(() => {
          if (document.visibilityState === 'visible') {
            console.log('📱 Auto re-requesting wake lock...');
            requestWakeLock();
          }
        }, 1000);
      });
      
      return true;
    } catch (error) {
      console.log('📱 Wake Lock API failed, trying fallback methods...');
    }
  }
  
  // Always start CSS animation method (very lightweight)
  initCSSKeepAwake();
  
  // Always start WebRTC method (additional layer)
  initWebRTCKeepAwake();
  
  // Fallback 1: Visible video method (works on most mobile browsers)
  if (tryVideoKeepAwake()) {
    keepAwakeMethod = 'video';
    keepAwakeActive = true;
    console.log('📱 Video method: Screen awake mode activated');
    updateKeepAwakeStatus();
    return true;
  }
  
  // Fallback 2: Periodic interaction simulation
  if (tryPeriodicKeepAwake()) {
    keepAwakeMethod = 'periodic';
    keepAwakeActive = true;
    console.log('📱 Periodic method: Screen awake mode activated');
    updateKeepAwakeStatus();
    return true;
  }
  
  // Last resort: Offer fullscreen mode (user interaction required)
  keepAwakeMethod = 'fullscreen';
  keepAwakeActive = false;
  console.log('📱 Only fullscreen mode available');
  updateKeepAwakeStatus();
  return false;
}

function updateKeepAwakeStatus() {
  // Update or create keep awake indicator
  let indicator = document.getElementById('keepAwakeIndicator');
  
  if (!indicator) {
    indicator = document.createElement('div');
    indicator.id = 'keepAwakeIndicator';
    indicator.style.cssText = `
      position: fixed;
      top: 10px;
      right: 10px;
      background: rgba(0, 0, 0, 0.7);
      color: white;
      padding: 6px 12px;
      border-radius: 15px;
      font-size: 11px;
      z-index: 1000;
      backdrop-filter: blur(5px);
      transition: all 0.3s ease;
      pointer-events: auto;
      cursor: pointer;
      user-select: none;
      border: 1px solid rgba(255, 255, 255, 0.1);
    `;
    document.body.appendChild(indicator);
    
    // Add click to toggle keep awake
    indicator.addEventListener('click', () => {
      if (keepAwakeActive) {
        stopKeepAwake();
        const toast = getShowKeepAwakeToast();
    if (toast) toast('Screen keep awake disabled');
      } else if (keepAwakeMethod === 'fullscreen') {
        // Request fullscreen mode
        requestFullscreenKeepAwake();
      } else {
        requestWakeLock();
                  const toast = getShowKeepAwakeToast();
          if (toast) toast('Screen keep awake enabled');
      }
    });
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
      if (indicator.style.opacity !== '0.5') {
        indicator.style.opacity = '0.5';
        indicator.style.transform = 'scale(0.9)';
      }
    }, 5000);
  }
  
  if (keepAwakeActive) {
    switch (keepAwakeMethod) {
      case 'wakeLock':
        indicator.innerHTML = '🔒 Keep Awake (API)';
        indicator.style.background = 'rgba(34, 197, 94, 0.8)';
        indicator.style.borderColor = 'rgba(34, 197, 94, 0.3)';
        break;
      case 'video':
        indicator.innerHTML = '🎥 Keep Awake (Active)';
        indicator.style.background = 'rgba(59, 130, 246, 0.8)';
        indicator.style.borderColor = 'rgba(59, 130, 246, 0.3)';
        break;
      case 'periodic':
        indicator.innerHTML = '⏰ Keep Awake (Touch)';
        indicator.style.background = 'rgba(168, 85, 247, 0.8)';
        indicator.style.borderColor = 'rgba(168, 85, 247, 0.3)';
        break;
      case 'fullscreen':
        indicator.innerHTML = '📺 Keep Awake (Fullscreen)';
        indicator.style.background = 'rgba(245, 158, 11, 0.8)';
        indicator.style.borderColor = 'rgba(245, 158, 11, 0.3)';
        break;
    }
  } else {
    switch (keepAwakeMethod) {
      case 'fullscreen':
        indicator.innerHTML = '📺 Tap for Fullscreen';
        indicator.style.background = 'rgba(245, 158, 11, 0.8)';
        indicator.style.borderColor = 'rgba(245, 158, 11, 0.3)';
        break;
      case 'none':
        indicator.innerHTML = '❌ Keep Awake N/A';
        indicator.style.background = 'rgba(107, 114, 128, 0.8)';
        indicator.style.borderColor = 'rgba(107, 114, 128, 0.3)';
        break;
      default:
        indicator.innerHTML = '😴 Tap to Keep Awake';
        indicator.style.background = 'rgba(239, 68, 68, 0.8)';
        indicator.style.borderColor = 'rgba(239, 68, 68, 0.3)';
    }
  }
}

function requestFullscreenKeepAwake() {
  if (document.fullscreenElement) {
    // Exit fullscreen
    document.exitFullscreen().then(() => {
      keepAwakeActive = false;
      updateKeepAwakeStatus();
              const toast = getShowKeepAwakeToast();
        if (toast) toast('Exited fullscreen mode');
    }).catch(() => {
              const toast = getShowKeepAwakeToast();
        if (toast) toast('Failed to exit fullscreen');
    });
  } else {
    // Enter fullscreen
    const element = document.documentElement;
    const requestFullscreen = element.requestFullscreen || 
                             element.webkitRequestFullscreen || 
                             element.mozRequestFullScreen || 
                             element.msRequestFullscreen;
    
    if (requestFullscreen) {
      requestFullscreen.call(element).then(() => {
        keepAwakeActive = true;
        updateKeepAwakeStatus();
        const toast = getShowKeepAwakeToast();
      if (toast) toast('Fullscreen mode activated - screen will stay awake');
        
        // Listen for fullscreen changes
        const handleFullscreenChange = () => {
          if (!document.fullscreenElement) {
            keepAwakeActive = false;
            updateKeepAwakeStatus();
            const toast = getShowKeepAwakeToast();
            if (toast) toast('Fullscreen exited - screen may sleep');
            document.removeEventListener('fullscreenchange', handleFullscreenChange);
            document.removeEventListener('webkitfullscreenchange', handleFullscreenChange);
            document.removeEventListener('mozfullscreenchange', handleFullscreenChange);
            document.removeEventListener('msfullscreenchange', handleFullscreenChange);
          }
        };
        
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
        document.addEventListener('mozfullscreenchange', handleFullscreenChange);
        document.addEventListener('msfullscreenchange', handleFullscreenChange);
        
      }).catch(() => {
        const toast = getShowKeepAwakeToast();
      if (toast) toast('Fullscreen request failed');
      });
    } else {
              const toast = getShowKeepAwakeToast();
        if (toast) toast('Fullscreen not supported');
      keepAwakeMethod = 'none';
      updateKeepAwakeStatus();
    }
  }
}

function tryVideoKeepAwake() {
  try {
    // Remove existing video if any
    if (hiddenVideo) {
      hiddenVideo.remove();
      hiddenVideo = null;
    }
    
    // Create barely visible video element (more effective than completely hidden)
    hiddenVideo = document.createElement('video');
    hiddenVideo.setAttribute('playsinline', 'true');
    hiddenVideo.setAttribute('webkit-playsinline', 'true');
    hiddenVideo.setAttribute('muted', 'true');
    hiddenVideo.setAttribute('autoplay', 'true');
    hiddenVideo.setAttribute('loop', 'true');
    hiddenVideo.setAttribute('controls', 'false');
    hiddenVideo.setAttribute('disablepictureinpicture', 'true');
    
    // Position video in bottom-right corner, barely visible but still "active"
    hiddenVideo.style.cssText = `
      position: fixed;
      bottom: 3px;
      right: 3px;
      width: 4px;
      height: 4px;
      opacity: 0.02;
      pointer-events: none;
      z-index: 998;
      border-radius: 1px;
      background: transparent;
    `;
    
    // Create animated canvas stream (more reliable than data URLs)
    const canvas = document.createElement('canvas');
    canvas.width = 8;
    canvas.height = 8;
    const ctx = canvas.getContext('2d');
    
    // Create subtle animation
    let frame = 0;
    const animateCanvas = () => {
      // Very subtle color changes - almost invisible
      const intensity = Math.sin(frame * 0.1) * 0.1 + 0.1;
      ctx.fillStyle = `rgba(0, 0, 0, ${intensity})`;
      ctx.fillRect(0, 0, 8, 8);
      frame++;
      requestAnimationFrame(animateCanvas);
    };
    animateCanvas();
    
    // Convert canvas to video stream
    const stream = canvas.captureStream(2); // 2 FPS for smoother animation
    hiddenVideo.srcObject = stream;
    
    document.body.appendChild(hiddenVideo);
    
    // Aggressive video management
    hiddenVideo.volume = 0;
    hiddenVideo.muted = true;
    
    // Function to force video playback
    const forceVideoPlay = async () => {
      try {
        await hiddenVideo.play();
        console.log('📱 Barely visible video playing successfully');
        
        // Very aggressive checks to keep video alive
        const videoKeepAliveInterval = setInterval(() => {
          if (!hiddenVideo) {
            clearInterval(videoKeepAliveInterval);
            return;
          }
          
          // Check if video is paused or ended
          if (hiddenVideo.paused || hiddenVideo.ended) {
            hiddenVideo.currentTime = 0;
            hiddenVideo.play().catch(() => {});
          }
          
          // Simulate interaction to keep video active
          hiddenVideo.dispatchEvent(new Event('timeupdate'));
          hiddenVideo.dispatchEvent(new Event('progress'));
          
        }, 300); // Check every 300ms - very frequent
        
        // Additional interaction simulation
        setInterval(() => {
          if (hiddenVideo) {
            hiddenVideo.dispatchEvent(new Event('canplay'));
            hiddenVideo.dispatchEvent(new Event('playing'));
          }
        }, 2000);
        
        return true;
        
      } catch (error) {
        console.log('📱 Canvas stream failed, trying data URL fallback...', error);
        
        // Fallback to data URL with same visible positioning
        hiddenVideo.srcObject = null;
        hiddenVideo.innerHTML = `
          <source src="data:video/webm;base64,GkXfo0AgQoaBAUL3gQFC8oEEQvOBCEKCQAR3ZWJtQoeBAkKFgQIYU4BnQI0VSalmQCgq17FAAw9CQE2AQAZ3aGFtbXlXQUAGd2hhbW15RIlACECPQAAAAAAAFlSua0AxrkAu14EBY8WBAZyBACK1nEADdW5khkAFVl9WUDglhohAA1ZQOIOBAeBABrCBCLqBCB9DtnVAIueBAKNAHIEAAIcBASPAgQjgAQAAAAAAABZUrmtAMa5ALteBAWPFgQGcgQAitZxAA3VuZIZABVZfVlA4JYaIQANWUDiDgQHgQAawgQi6gQgfQ7Z1QCLngQCjQByBAAMAAEALdq1+MQAK77+9z4Xs3QEtBIAGSIPLfENM3Heh9kfGvgAA" type="video/webm">
          <source src="data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAAAhFtZGF0AAAC6gYF//+c3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE1MiByMjg1NCBlOWE1OTAzIC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAxNyAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MzoweDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTMgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9MCBkaXJlY3Q9MSB3ZWlnaHRiPTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTI1IHNjZW5lY3V0PTQwIGludHJhX3JlZnJlc2g9MCByY19sb29rYWhlYWQ9NDAgcmM9Y3JmIG1idHJlZT0xIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRpbz0xLjQwIGFxPTE6MS4wMACAAAABWWWIhAA3//727P4FNjuY0JcRzeidDKmKQClAQEAAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAMAQAAAAwAAAwAAAwAAAwAAAwAAAAAaAAADIGdtb29mAAAM4HRyYWsAAABcdGtoZAAAAAPsAAAAAAAAAAAAAAAAAAAAAAACAAAAYAAAAAEAAQAAAAAAAAAAAAAAAAAAAAAAAP//AAAAQAAAAAAAAAAAAAAAAAAAAEsW" type="video/mp4">
        `;
        hiddenVideo.load();
        return await hiddenVideo.play();
      }
    };
    
    // Try to start video immediately or wait for user interaction
    forceVideoPlay().catch(() => {
      console.log('📱 Video needs user interaction to start');
      
      // Create a more visible tooltip prompting user interaction
      const interactionPrompt = document.createElement('div');
      interactionPrompt.style.cssText = `
        position: fixed;
        bottom: 10px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 8px 15px;
        border-radius: 15px;
        font-size: 12px;
        z-index: 1000;
        pointer-events: none;
        backdrop-filter: blur(5px);
        border: 1px solid rgba(255, 255, 255, 0.1);
      `;
      interactionPrompt.textContent = 'Tap anywhere to activate screen protection';
      document.body.appendChild(interactionPrompt);
      
      // Auto-hide prompt after 5 seconds
      setTimeout(() => {
        if (interactionPrompt.parentNode) {
          interactionPrompt.remove();
        }
      }, 5000);
      
      // Wait for any user interaction to start video
      const startVideoOnInteraction = () => {
        forceVideoPlay().then(() => {
          if (interactionPrompt.parentNode) {
            interactionPrompt.remove();
          }
          document.removeEventListener('touchstart', startVideoOnInteraction);
          document.removeEventListener('click', startVideoOnInteraction);
          document.removeEventListener('keydown', startVideoOnInteraction);
        });
      };
      
      document.addEventListener('touchstart', startVideoOnInteraction, { once: true, passive: true });
      document.addEventListener('click', startVideoOnInteraction, { once: true });
      document.addEventListener('keydown', startVideoOnInteraction, { once: true });
    });
    
    return true;
  } catch (error) {
    console.log('📱 Video keep awake method failed completely:', error);
    if (hiddenVideo) {
      hiddenVideo.remove();
      hiddenVideo = null;
    }
    return false;
  }
}

// Export functions for browser environment
window.KeepAwake = {
  initKeepAwakeHandlers,
  requestWakeLock,
  stopKeepAwake,
  updateKeepAwakeStatus,
  requestFullscreenKeepAwake,
  tryVideoKeepAwake,
  tryPeriodicKeepAwake,
  initCSSKeepAwake,
  initWebRTCKeepAwake
}; 