/**
 * Confirm Dialog (mobile-friendly)
 * Promise-based modal confirmation dialog.
 *
 * Usage:
 *   const ok = await window.showConfirmDialog({
 *     title: 'Delete Track',
 *     message: 'Are you sure?',
 *     // or: htmlMessage: 'Line 1<br/>Line 2',
 *     confirmText: 'Delete',
 *     cancelText: 'Cancel',
 *     destructive: true
 *   });
 *
 * Returns true on confirm, false on cancel/close.
 */
(function initConfirmDialogModule() {
  const FOCUSABLE_SELECTOR = [
    'a[href]',
    'area[href]',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    'button:not([disabled])',
    'iframe',
    'object',
    'embed',
    '[tabindex]:not([tabindex="-1"])',
    '[contenteditable="true"]'
  ].join(',');

  function createElement(tag, className, attrs = {}) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    for (const [key, value] of Object.entries(attrs)) {
      if (key === 'text') {
        el.textContent = value;
      } else if (key === 'html') {
        el.innerHTML = value;
      } else {
        el.setAttribute(key, value);
      }
    }
    return el;
  }

  function lockScroll() {
    const previous = document.body.style.overflow;
    document.body.dataset.prevOverflow = previous || '';
    document.body.style.overflow = 'hidden';
  }

  function unlockScroll() {
    const previous = document.body.dataset.prevOverflow;
    if (previous !== undefined) {
      document.body.style.overflow = previous;
      delete document.body.dataset.prevOverflow;
    } else {
      document.body.style.overflow = '';
    }
  }

  function setupFocusTrap(container, initialFocusEl) {
    const focusable = Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR))
      .filter(el => el.offsetParent !== null || el instanceof window.SVGElement);

    const first = focusable[0] || container;
    const last = focusable[focusable.length - 1] || container;

    function onKeyDown(e) {
      if (e.key === 'Tab') {
        if (focusable.length === 0) {
          e.preventDefault();
          container.focus();
          return;
        }
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    container.addEventListener('keydown', onKeyDown);
    (initialFocusEl || first).focus();

    return () => container.removeEventListener('keydown', onKeyDown);
  }

  function uniqueId(prefix) {
    return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
  }

  async function showConfirmDialog(options) {
    const {
      title = 'Confirm',
      message = '',
      htmlMessage,
      confirmText,
      cancelText = 'Cancel',
      destructive = false
    } = options || {};

    return new Promise(resolve => {
      let resolved = false;
      function safeResolve(value) {
        if (!resolved) {
          resolved = true;
          resolve(value);
        }
      }

      const activeBeforeOpen = document.activeElement;

      const modal = createElement('div', 'modal', {
        role: 'dialog',
        'aria-modal': 'true'
      });

      const titleId = uniqueId('confirm-title');
      const descId = uniqueId('confirm-desc');
      modal.setAttribute('aria-labelledby', titleId);
      modal.setAttribute('aria-describedby', descId);

      const content = createElement('div', 'modal-content');
      if (destructive) content.classList.add('modal-destructive');

      const header = createElement('div', 'modal-header');
      const titleEl = createElement('h3', 'modal-title', { id: titleId, text: title });
      const closeBtn = createElement('button', 'modal-close', { 'aria-label': 'Close', type: 'button' });
      closeBtn.innerHTML = '&times;';
      header.appendChild(titleEl);
      header.appendChild(closeBtn);

      const body = createElement('div', 'modal-body', { id: descId });
      if (htmlMessage != null) {
        body.innerHTML = htmlMessage;
      } else {
        body.textContent = message;
      }

      const actions = createElement('div', 'modal-actions');
      const cancelBtn = createElement('button', 'btn btn-secondary', { type: 'button', text: cancelText });
      const okText = confirmText || (destructive ? 'Delete' : 'OK');
      const confirmBtn = createElement('button', `btn ${destructive ? 'btn-danger' : 'btn-primary'}`, { type: 'button', text: okText });
      actions.appendChild(cancelBtn);
      actions.appendChild(confirmBtn);

      content.appendChild(header);
      content.appendChild(body);
      content.appendChild(actions);
      modal.appendChild(content);
      document.body.appendChild(modal);

      lockScroll();

      // Focus management
      content.setAttribute('tabindex', '-1');
      const removeFocusTrap = setupFocusTrap(content, confirmBtn);

      function cleanup() {
        removeFocusTrap();
        modal.removeEventListener('click', onBackdropClick);
        document.removeEventListener('keydown', onDocKeyDown);
        unlockScroll();
        modal.remove();
        if (activeBeforeOpen && typeof activeBeforeOpen.focus === 'function') {
          activeBeforeOpen.focus();
        }
      }

      function onBackdropClick(e) {
        if (e.target === modal) {
          safeResolve(false);
          cleanup();
        }
      }

      function onDocKeyDown(e) {
        if (e.key === 'Escape') {
          e.preventDefault();
          safeResolve(false);
          cleanup();
        } else if (e.key === 'Enter') {
          // Confirm on Enter for convenience
          e.preventDefault();
          safeResolve(true);
          cleanup();
        }
      }

      modal.addEventListener('click', onBackdropClick);
      document.addEventListener('keydown', onDocKeyDown);

      // Button handlers
      closeBtn.addEventListener('click', () => { safeResolve(false); cleanup(); });
      cancelBtn.addEventListener('click', () => { safeResolve(false); cleanup(); });
      confirmBtn.addEventListener('click', () => { safeResolve(true); cleanup(); });
    });
  }

  // Expose globally
  window.showConfirmDialog = showConfirmDialog;
})();


