// Time formatting utility functions extracted from player-utils.js

/**
 * Format time in seconds to MM:SS format
 * @param {number} s - time in seconds
 * @returns {string} - formatted time
 */
export function formatTime(s) {
  if (!isFinite(s)) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60).toString().padStart(2, '0');
  return `${m}:${sec}`;
} 