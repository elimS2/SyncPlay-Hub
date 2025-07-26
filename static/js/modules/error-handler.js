// Error handling utilities extracted from player-utils.js

/**
 * Log error to console with timestamp and context
 * @param {string} message - error message
 * @param {Error} error - error object (optional)
 * @param {Object} context - additional context (optional)
 */
export function logError(message, error = null, context = null) {
    const timestamp = new Date().toISOString();
    const errorInfo = {
        timestamp,
        message,
        error: error ? error.message : null,
        stack: error ? error.stack : null,
        context
    };
    
    console.error('🚨 [ERROR]', errorInfo);
    
    // In production, you might want to send this to a logging service
    // sendToLoggingService(errorInfo);
}

/**
 * Show error toast notification to user
 * @param {string} message - error message to display
 * @param {string} title - error title (optional)
 * @param {number} duration - display duration in milliseconds (default: 5000)
 */
export function showErrorToast(message, title = 'Error', duration = 5000) {
    // Create error notification element
    const notification = document.createElement('div');
    notification.className = 'notification notification-error';
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 16px 20px;
        border-radius: 6px;
        background-color: #f44336;
        color: white;
        font-weight: 500;
        z-index: 10000;
        max-width: 400px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        transition: opacity 0.3s ease, transform 0.3s ease;
        transform: translateX(100%);
        border-left: 4px solid #d32f2f;
    `;
    
    // Add title if provided
    if (title) {
        notification.innerHTML = `
            <div style="font-weight: 600; margin-bottom: 4px;">${title}</div>
            <div>${message}</div>
        `;
    } else {
        notification.textContent = message;
    }
    
    // Add to document
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 100);
    
    // Auto remove after specified duration
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, duration);
    
    // Log error for debugging
    logError(message, null, { title, duration });
}

/**
 * Handle and display errors from async operations
 * @param {Function} asyncFunction - async function to wrap
 * @param {string} errorMessage - fallback error message
 * @param {boolean} showToast - whether to show error toast (default: true)
 * @returns {Function} wrapped function that handles errors
 */
export function withErrorHandling(asyncFunction, errorMessage = 'An error occurred', showToast = true) {
    return async (...args) => {
        try {
            return await asyncFunction(...args);
        } catch (error) {
            const message = error.message || errorMessage;
            logError(message, error, { functionName: asyncFunction.name, args });
            
            if (showToast) {
                showErrorToast(message, 'Operation Failed');
            }
            
            throw error; // Re-throw to allow caller to handle if needed
        }
    };
} 