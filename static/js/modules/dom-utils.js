// DOM utilities and helper functions extracted from player-utils.js

/**
 * Format file size in bytes to readable format
 * @param {number} bytes - file size in bytes
 * @returns {string} formatted file size
 */
export function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  
  if (i === 0) return bytes + ' ' + sizes[i];
  
  return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + sizes[i];
} 