/**
 * Border Sentinel — Tauri Bridge v2
 * ─────────────────────────────────
 * Вставить в index.html перед закрывающим </body>:
 *   <script type="module" src="tauri-bridge.js"></script>
 *
 * Работает в двух режимах:
 *   • Tauri  — нативные команды через invoke()
 *   • Browser — graceful fallback, ничего не ломает
 */

// ── 1. Определяем среду ──────────────────────────────────────────────────────
const IS_TAURI = window.__TAURI_INTERNALS__ !== undefined;

// ── 2. Lazy-load Tauri API ───────────────────────────────────────────────────
let $invoke = null;
let $listen = null;
let $emit   = null;

async function tauri() {
  if (!IS_TAURI) return {};
  if ($invoke) return { invoke: $invoke, listen: $listen, emit: $emit };

  // Tauri v2 — API доступен как глобал через __TAURI_INTERNALS__
  // При сборке через Tauri CLI эти модули бандлятся автоматически
  const { invoke } = await import('/core.js').catch(() =>
    window.__TAURI_INTERNALS__
      ? { invoke: window.__TAURI_INTERNALS__.invoke }
      : { invoke: null }
  );

  // Fallback: использовать глобальный объект Tauri
  $invoke = invoke || window.__TAURI__?.core?.invoke || window.__TAURI__?.tauri?.invoke;
  $listen = window.__TAURI__?.event?.listen;
  $emit   = window.__TAURI__?.event?.emit;

  return { invoke: $invoke, listen: $listen, emit: $emit };
}

// ── 3. Notify — заменяем alert() / браузерные уведомления ───────────────────
/**
 * @param {string} title
 * @param {string} body
 * @param {boolean} urgent — OS уведомление даже когда окно скрыто
 */
window.nativeNotify = async function(title, body, urgent = false) {
  if (!IS_TAURI) {
    // Browser fallback — используем Notification API если есть
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(title, { body });
    }
    return;
  }
  try {
    const { invoke } = await tauri();
    if (invoke) await invoke('notify', { title, body, urgent });
  } catch(e) {
    console.warn('[Bridge] notify error:', e);
  }
};

// Патчим браузерный alert глобально
const _origAlert = window.alert;
window.alert = function(msg) {
  // Показываем in-app toast если функция определена в app
  if (typeof window.toast === 'function') {
    window.toast(String(msg), 'info');
  } else {
    _origAlert(msg);
  }
};

// ── 4. Backend Health Check с лоадером ──────────────────────────────────────
let _healthInterval = null;
let _backendReady   = false;

/**
 * Показывает splash-экран пока бэкенд не ответит.
 * Вызывается автоматически при старте.
 */
async function checkBackendHealth() {
  if (!IS_TAURI) {
    // В браузере просто проверяем HTTP
    try {
      const r = await fetch('http://127.0.0.1:8000/api/stats', { signal: AbortSignal.timeout(2000) });
      _backendReady = r.ok;
    } catch { _backendReady = false; }
    updateStatusUI(_backendReady);
    return _backendReady;
  }

  try {
    const { invoke } = await tauri();
    if (!invoke) return false;
    _backendReady = await invoke('backend_health');
    updateStatusUI(_backendReady);
    return _backendReady;
  } catch {
    updateStatusUI(false);
    return false;
  }
}

/** Обновляет status pill и splash в UI */
function updateStatusUI(ready) {
  // Status pill (из твоего index.html)
  const pill   = document.getElementById('statusPill');
  const pillTx = document.getElementById('statusText');
  const splash = document.getElementById('bs-splash');

  if (pill) pill.className = 'status-pill ' + (ready ? 'online' : 'offline');
  if (pillTx) pillTx.textContent = ready ? 'Backend online' : 'Backend offline';

  if (splash) {
    if (ready) {
      splash.style.opacity = '0';
      setTimeout(() => { splash.style.display = 'none'; }, 300);
    } else {
      splash.style.display = 'flex';
      splash.style.opacity = '1';
    }
  }
}

/**
 * Публичная функция — вызвать из кода приложения
 * Возвращает Promise<boolean>
 */
window.checkBackendHealth = checkBackendHealth;

/** Polling пока бэкенд не поднимется (только для browser-режима) */
function startHealthPolling() {
  if (_healthInterval) return;
  _healthInterval = setInterval(async () => {
    const ok = await checkBackendHealth();
    if (ok) {
      clearInterval(_healthInterval);
      _healthInterval = null;
    }
  }, 3000);
}

// ── 5. Drag & Drop файлов ────────────────────────────────────────────────────
/**
 * Читает файл через Tauri fs (для PDF/TXT дропа в окно)
 * @param {string} path — абсолютный путь из tauri://drag-drop события
 * @returns {Promise<string|null>}
 */
window.readDroppedFile = async function(path) {
  if (!IS_TAURI) return null;
  try {
    const { invoke } = await tauri();
    return await invoke('read_file', { path });
  } catch(e) {
    console.warn('[Bridge] read_file error:', path, e);
    return null;
  }
};

/** Вешаем обработчик drag-drop через Tauri events */
async function setupDragDrop() {
  if (!IS_TAURI || !$listen) return;

  await $listen('tauri://drag-drop', async (event) => {
    const paths = event.payload?.paths || [];
    console.log('[Bridge] Files dropped:', paths);

    for (const path of paths) {
      const ext = path.split('.').pop().toLowerCase();
      let content = null;

      // Читаем только текстовые форматы
      if (['txt', 'md', 'json', 'csv', 'log'].includes(ext)) {
        content = await window.readDroppedFile(path);
      }

      // Диспатчим событие — пусть приложение само решает что делать
      window.dispatchEvent(new CustomEvent('bs:file-dropped', {
        detail: { path, ext, content, size: content?.length || 0 }
      }));

      // Toast уведомление
      const filename = path.split('/').pop().split('\\').pop();
      if (typeof window.toast === 'function') {
        window.toast(`File dropped: ${filename}`, 'info');
      }
    }
  });

  // Визуальный overlay при наведении файла
  await $listen('tauri://drag-enter', () => {
    document.body.classList.add('drag-over');
  });
  await $listen('tauri://drag-leave', () => {
    document.body.classList.remove('drag-over');
  });
}

// ── 6. Tauri event listeners ─────────────────────────────────────────────────
async function setupEventListeners() {
  if (!IS_TAURI) return;

  // Ждём пока $listen будет готов
  await tauri();
  if (!$listen) { console.warn('[Bridge] $listen not available'); return; }

  // backend-ready от Rust (после успешного health check в lib.rs)
  await $listen('backend-ready', () => {
    console.log('[Bridge] ✅ backend-ready event');
    _backendReady = true;
    updateStatusUI(true);
    if (_healthInterval) { clearInterval(_healthInterval); _healthInterval = null; }
    document.dispatchEvent(new CustomEvent('bs:backend-ready'));
    if (typeof window.toast === 'function') {
      window.toast('Backend online', 'success');
    }
  });

  // backend-error от Rust
  await $listen('backend-error', (event) => {
    console.error('[Bridge] ❌ backend-error:', event.payload);
    _backendReady = false;
    updateStatusUI(false);
    document.dispatchEvent(new CustomEvent('bs:backend-error', { detail: event.payload }));
    if (typeof window.toast === 'function') {
      window.toast('Backend failed to start — check logs', 'error');
    }
  });

  // focus-search — из tray меню или Ctrl+Shift+S
  await $listen('focus-search', () => {
    console.log('[Bridge] focus-search event');
    // Пробуем найти поле поиска по разным возможным id
    const search =
      document.getElementById('gSearch') ||
      document.getElementById('globalSearch') ||
      document.getElementById('sqQuery') ||
      document.querySelector('input[type="search"]') ||
      document.querySelector('input[placeholder*="earch"]');

    if (search) {
      // Показываем окно и фокусируем
      const win = document.querySelector('.main-content, main, #mc');
      if (win) win.scrollTo({ top: 0, behavior: 'smooth' });
      search.focus();
      search.select();
      // Подсвечиваем анимацией
      search.style.transition = 'box-shadow 0.2s';
      search.style.boxShadow = '0 0 0 3px rgba(208,188,255,0.4)';
      setTimeout(() => { search.style.boxShadow = ''; }, 1000);
    }
  });
}

// ── 7. Перехват внешних ссылок ───────────────────────────────────────────────
function setupLinkIntercept() {
  if (!IS_TAURI) return;

  document.addEventListener('click', async (e) => {
    const link = e.target.closest('a[href]');
    if (!link) return;
    const href = link.getAttribute('href');
    if (!href) return;

    const isExternal = href.startsWith('http://') || href.startsWith('https://');
    const isLocalhost = href.includes('127.0.0.1') || href.includes('localhost');

    if (isExternal && !isLocalhost) {
      e.preventDefault();
      try {
        const { invoke } = await tauri();
        await invoke('open_url', { url: href });
      } catch(err) {
        console.warn('[Bridge] open_url failed:', err);
        window.open(href, '_blank');
      }
    }
  });
}

// ── 8. Keychain API ──────────────────────────────────────────────────────────
const KEYCHAIN_SERVICE = 'border-sentinel';

window.keychainSet = async function(key, value) {
  if (!IS_TAURI) { localStorage.setItem('bs_' + key, value); return true; }
  try {
    const { invoke } = await tauri();
    await invoke('keychain_set', { service: KEYCHAIN_SERVICE, key, value });
    return true;
  } catch(e) {
    console.warn('[Bridge] keychainSet error:', e);
    // Fallback to localStorage on error
    localStorage.setItem('bs_' + key, value);
    return false;
  }
};

window.keychainGet = async function(key) {
  if (!IS_TAURI) return localStorage.getItem('bs_' + key);
  try {
    const { invoke } = await tauri();
    return await invoke('keychain_get', { service: KEYCHAIN_SERVICE, key });
  } catch {
    // Key не найден в keychain — проверяем localStorage fallback
    return localStorage.getItem('bs_' + key);
  }
};

window.keychainDelete = async function(key) {
  if (!IS_TAURI) { localStorage.removeItem('bs_' + key); return; }
  try {
    const { invoke } = await tauri();
    await invoke('keychain_delete', { service: KEYCHAIN_SERVICE, key });
  } catch(e) {
    console.warn('[Bridge] keychainDelete error:', e);
  }
};

// Хелпер для API ключей
window.saveApiKey   = async (key, val) => { await window.keychainSet(key, val); };
window.loadApiKey   = async (key)      => window.keychainGet(key);

// ── 9. High-priority alert hook ──────────────────────────────────────────────
/**
 * Вызывай когда найден HIGH-priority результат.
 * Показывает in-app toast + OS уведомление.
 */
window.alertHighPriority = async function(title, detail = '') {
  if (typeof window.toast === 'function') {
    window.toast('🚨 ' + title, 'error');
  }
  await window.nativeNotify('🚨 Border Sentinel', title + (detail ? '\n' + detail : ''), true);
};

// ── 10. Splash screen inject ─────────────────────────────────────────────────
function injectSplash() {
  if (document.getElementById('bs-splash')) return;
  const splash = document.createElement('div');
  splash.id = 'bs-splash';
  splash.innerHTML = `
    <div style="
      position:fixed;inset:0;z-index:9999;
      background:#1C1B1F;
      display:flex;flex-direction:column;
      align-items:center;justify-content:center;gap:18px;
      transition:opacity 0.3s;
    ">
      <div style="
        width:52px;height:52px;border-radius:14px;
        background:#4F378B;display:flex;align-items:center;
        justify-content:center;font-size:22px;font-weight:700;
        color:#EADDFF;letter-spacing:-0.5px;
      ">OI</div>
      <div style="font-size:18px;font-weight:600;color:#E6E1E5;letter-spacing:-0.3px">
        Border Sentinel
      </div>
      <div style="display:flex;align-items:center;gap:10px;color:#CAC4D0;font-size:13px">
        <div style="
          width:16px;height:16px;border:2px solid #49454F;
          border-top-color:#D0BCFF;border-radius:50%;
          animation:bsspin 0.7s linear infinite;
        "></div>
        Starting backend…
      </div>
      <style>@keyframes bsspin{to{transform:rotate(360deg)}}</style>
    </div>`;
  document.body.prepend(splash);
}

// ── 11. CSS для drag-over состояния ─────────────────────────────────────────
function injectDragStyle() {
  const s = document.createElement('style');
  s.textContent = `
    body.drag-over::after {
      content: '📂 Drop files here';
      position: fixed; inset: 0; z-index: 8888;
      background: rgba(79,55,139,0.55);
      backdrop-filter: blur(4px);
      display: flex; align-items: center; justify-content: center;
      font-size: 24px; font-weight: 600; color: #EADDFF;
      border: 3px dashed #D0BCFF;
      pointer-events: none;
    }
  `;
  document.head.appendChild(s);
}

// ── BOOT ─────────────────────────────────────────────────────────────────────
(async () => {
  console.log(`[Bridge] IS_TAURI=${IS_TAURI}`);

  injectDragStyle();

  if (IS_TAURI) {
    // Показываем splash пока бэкенд не поднялся
    injectSplash();

    // Инициализируем Tauri API
    await tauri();

    // Вешаем все listeners
    await setupEventListeners();
    await setupDragDrop();
    setupLinkIntercept();

    console.log('[Bridge] ✅ Tauri bridge ready');
  } else {
    // Browser mode — просто проверяем бэкенд по HTTP
    console.log('[Bridge] Browser mode — Tauri features disabled');
    const ok = await checkBackendHealth();
    if (!ok) startHealthPolling();
  }
})();

// ── BOOT FIX: race condition safe version ────────────────────────────────────
// Замінює попередній BOOT блок — чекає DOMContentLoaded + Tauri ready

(function() {
  // Видаляємо старий boot якщо вже запустився
  if (window.__BS_BRIDGE_BOOTED__) return;
  window.__BS_BRIDGE_BOOTED__ = true;

  async function boot() {
    console.log(`[Bridge] Boot start. IS_TAURI=${IS_TAURI}`);
    injectDragStyle();

    if (!IS_TAURI) {
      console.log('[Bridge] Browser mode');
      const ok = await checkBackendHealth();
      if (!ok) startHealthPolling();
      return;
    }

    // Tauri mode: чекаємо поки __TAURI_INTERNALS__ буде повністю готовий
    // Race condition fix: poll до 3 секунд
    let attempts = 0;
    while (!window.__TAURI_INTERNALS__?.invoke && attempts < 30) {
      await new Promise(r => setTimeout(r, 100));
      attempts++;
    }

    if (!window.__TAURI_INTERNALS__?.invoke) {
      console.error('[Bridge] Tauri API not available after 3s — falling back');
      const ok = await checkBackendHealth();
      if (!ok) startHealthPolling();
      return;
    }

    // Ініціалізуємо Tauri API
    $invoke = window.__TAURI_INTERNALS__.invoke;

    // Намагаємось дістати listen/emit
    try {
      const evt = window.__TAURI__?.event;
      if (evt) { $listen = evt.listen; $emit = evt.emit; }
    } catch(e) {
      console.warn('[Bridge] event API not available:', e);
    }

    // Показуємо splash
    injectSplash();

    // Вішаємо listeners (не блокуємо якщо listen недоступний)
    try { await setupEventListeners(); } catch(e) { console.warn('[Bridge] listeners:', e); }
    try { await setupDragDrop(); }       catch(e) { console.warn('[Bridge] dragdrop:', e); }
    setupLinkIntercept();

    console.log('[Bridge] ✅ Ready');
  }

  // Запускаємо після DOMContentLoaded — гарантовано без race condition
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    // DOM вже готовий
    boot();
  }
})();
