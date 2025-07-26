/**
 * Общие утилиты для плееров
 * Централизованное управление дублирующимися методами
 */

// Import functions moved to playlist-utils.js for backward compatibility
import { shuffle, smartShuffle, smartChannelShuffle, getGroupPlaybackInfo, detectChannelGroup, orderByPublishDate, triggerAutoDeleteCheck, loadTrack } from './player/playlist-utils.js';

// Import functions moved to time-format.js for backward compatibility
import { formatTime } from './time-format.js';

// Import functions moved to ui-effects.js for backward compatibility
import { updateSpeedDisplay, showNotification, showFsControls, updateFsVisibility, createTrackTooltipHTML, setupGlobalTooltip } from './ui-effects.js';

// Import functions moved to controls.js for backward compatibility
import { handleVolumeWheel, stopTick, stopPlayback, playIndex, updateMuteIcon, nextTrack, prevTrack, startTick, performKeyboardSeek, syncLikeButtonsWithRemote, syncLikesAfterAction, setupLikeSyncHandlers, togglePlayback, cyclePlaybackSpeed, deleteTrack, initializeGoogleCastIntegration, castLoad, setupMediaEndedHandler, setupMediaPlayPauseHandlers, setupMediaTimeUpdateHandler, setupMediaSeekedHandler, setupKeyboardHandler, setupProgressClickHandler, setupMediaSessionAPI, setupPlaylistToggleHandler, setupDeleteCurrentHandler, setupLikeDislikeHandlers, setupYouTubeHandler, setupFullscreenHandlers, setupSimpleControlHandlers, executeDeleteWithoutConfirmation, setupStreamHandler, setupBeforeUnloadHandler, setupAutoPlayInitialization, setupRemoteControlOverrides, setupRemoteControlInitialization } from './controls.js';

// Import functions moved to player-state.js for backward compatibility
import { saveVolumeToDatabase, loadSavedVolume, syncRemoteState } from './player-state.js';

// Import functions moved to dom-utils.js for backward compatibility
import { formatFileSize } from './dom-utils.js';

// Import functions moved to event-bus.js for backward compatibility
import { sendStreamEvent, reportEvent, recordSeekEvent, pollRemoteCommands, executeRemoteCommand } from './event-bus.js';

// Re-export for backward compatibility
export { shuffle, smartShuffle, smartChannelShuffle, getGroupPlaybackInfo, detectChannelGroup, orderByPublishDate, triggerAutoDeleteCheck, loadTrack, formatTime, updateSpeedDisplay, showNotification, showFsControls, updateFsVisibility, createTrackTooltipHTML, setupGlobalTooltip, handleVolumeWheel, stopTick, stopPlayback, playIndex, updateMuteIcon, nextTrack, prevTrack, startTick, performKeyboardSeek, syncLikeButtonsWithRemote, syncLikesAfterAction, setupLikeSyncHandlers, togglePlayback, cyclePlaybackSpeed, deleteTrack, initializeGoogleCastIntegration, castLoad, setupMediaEndedHandler, setupMediaPlayPauseHandlers, setupMediaTimeUpdateHandler, setupMediaSeekedHandler, setupKeyboardHandler, setupProgressClickHandler, setupMediaSessionAPI, setupPlaylistToggleHandler, setupDeleteCurrentHandler, setupLikeDislikeHandlers, setupYouTubeHandler, setupFullscreenHandlers, setupSimpleControlHandlers, executeDeleteWithoutConfirmation, setupStreamHandler, setupBeforeUnloadHandler, setupAutoPlayInitialization, setupRemoteControlOverrides, setupRemoteControlInitialization, saveVolumeToDatabase, loadSavedVolume, syncRemoteState, formatFileSize, sendStreamEvent, reportEvent, recordSeekEvent, pollRemoteCommands, executeRemoteCommand };

// ===== УТИЛИТЫ МАССИВОВ =====



// ===== АНАЛИЗ КАНАЛОВ =====

/**
 * Определяет тип канала/группы по пути файла
 * @param {Object} track - объект трека с полем relpath
 * @returns {Object} - объект с типом канала, группой и флагом isChannel
 */


/**
 * Умное перемешивание на основе типа канала
 * - Music: Случайное перемешивание
 * - News: Хронологический порядок (новые первыми)
 * - Education: Последовательный порядок (старые первыми)
 * - Podcasts: Последовательный порядок (новые первыми)
 * - Playlists: Умное перемешивание (существующая логика)
 * @param {Array} tracks - массив треков для обработки
 * @returns {Array} - обработанный массив треков
 */


/**
 * Получает информацию о воспроизведении для текущего микса треков
 * Анализирует треки и возвращает статистику по группам каналов
 * @param {Array} tracks - массив треков для анализа
 * @returns {Array|null} - массив с информацией о группах или null если треков нет
 */


// ===== СОРТИРОВКА ТРЕКОВ =====

/**
 * Sort tracks by YouTube publish date in ascending order (oldest first)
 * Supports different field naming schemas for regular playlists vs virtual playlists
 * @param {Array} tracks - Array of track objects to sort
 * @param {string} schema - Field naming schema: 'regular' (youtube_*) or 'virtual' (no prefix)
 * @returns {Array} Sorted array of tracks (oldest first)
 */


// ===== ВСПОМОГАТЕЛЬНЫЕ УТИЛИТЫ =====

/**
 * Форматирует время в секундах в формат MM:SS
 * @param {number} s - время в секундах
 * @returns {string} - отформатированное время
 */








// ===== УПРАВЛЕНИЕ ВОСПРОИЗВЕДЕНИЕМ =====









// ===== НАВИГАЦИЯ ПО ТРЕКАМ =====





// ===== ПОТОКОВЫЕ СОБЫТИЯ =====





// ===== ОБРАБОТКА СОБЫТИЙ =====





// ===== УПРАВЛЕНИЕ НАСТРОЙКАМИ =====



// ===== REMOTE CONTROL И СИНХРОНИЗАЦИЯ =====













// ==============================
// КОНТРОЛЬ ВОСПРОИЗВЕДЕНИЯ
// ==============================



// ==============================
// ПОЛНОЭКРАННЫЙ РЕЖИМ
// ==============================







// ==============================
// ПОЛЬЗОВАТЕЛЬСКИЙ ИНТЕРФЕЙС
// ==============================









 

// ==============================
// REMOTE CONTROL COMMANDS  
// ==============================



// ==============================
// TRACK DELETION
// ==============================

 

// ==============================
// GOOGLE CAST INTEGRATION
// ==============================





 

// ===================================
// 11. EVENT HANDLERS & MEDIA CONTROLS
// ===================================















 

// ===== 12. UI INTERACTIONS & CONTROL HANDLERS =====

/**
 * Настраивает обработчик кнопки удаления текущего трека
 * @param {HTMLElement} deleteCurrentBtn - кнопка удаления
 * @param {Object} context - контекст с необходимыми данными
 * @param {Object} context.currentIndex - текущий индекс
 * @param {Array} context.queue - очередь треков  
 * @param {Array} context.tracks - массив треков
 * @param {HTMLElement} context.media - медиа элемент
 * @param {Function} context.playIndex - функция воспроизведения по индексу
 * @param {Function} context.renderList - функция обновления списка
 * @param {Function} context.showNotification - функция показа уведомлений
 * @param {Function} context.loadTrack - функция загрузки трека
 * @param {string} playerType - тип плеера ('regular' или 'virtual')
 */




















