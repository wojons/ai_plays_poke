/*
 * Visual RAM overlay for the EmulatorJS Game Boy viewer.
 * Vanilla JS only, self-contained, throttled to ~4 FPS via requestAnimationFrame.
 */
(function (global, document) {
  'use strict';

  const UPDATE_INTERVAL_MS = 250;
  let overlay;
  let lastRender = 0;
  let visible = true;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function injectStyles() {
    if (document.getElementById('ram-overlay-styles')) {
      return;
    }

    const style = document.createElement('style');
    style.id = 'ram-overlay-styles';
    style.textContent = `
      #ram-overlay {
        position: absolute;
        top: 14px;
        right: 14px;
        z-index: 2147483000;
        min-width: 260px;
        max-width: min(390px, calc(100% - 28px));
        padding: 12px 14px;
        border: 1px solid rgba(101, 255, 122, 0.55);
        border-radius: 10px;
        background: rgba(1, 8, 3, 0.86);
        box-shadow: 0 0 24px rgba(0, 255, 80, 0.16), inset 0 0 16px rgba(101, 255, 122, 0.05);
        color: #65ff7a;
        font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        pointer-events: none;
        text-shadow: 0 0 8px rgba(101, 255, 122, 0.32);
        white-space: normal;
      }

      #ram-overlay[hidden] {
        display: none !important;
      }

      #ram-overlay .ram-title {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 8px;
        padding-bottom: 6px;
        border-bottom: 1px solid rgba(101, 255, 122, 0.24);
        color: #d3ffd8;
        font-weight: 800;
        letter-spacing: 0.05em;
        text-transform: uppercase;
      }

      #ram-overlay .ram-badge {
        color: #050806;
        background: #65ff7a;
        border-radius: 999px;
        padding: 0 7px;
        text-shadow: none;
      }

      #ram-overlay dl {
        display: grid;
        grid-template-columns: 96px minmax(0, 1fr);
        gap: 3px 10px;
        margin: 0;
      }

      #ram-overlay dt {
        color: #83ad89;
      }

      #ram-overlay dd {
        margin: 0;
        color: #d3ffd8;
        overflow-wrap: anywhere;
      }

      #ram-overlay .party {
        margin-top: 8px;
        padding-top: 7px;
        border-top: 1px solid rgba(101, 255, 122, 0.24);
      }

      #ram-overlay .party-title {
        margin-bottom: 3px;
        color: #83ad89;
      }

      #ram-overlay .party ul {
        margin: 0;
        padding: 0;
        list-style: none;
      }

      #ram-overlay .party li {
        color: #d3ffd8;
      }
    `;
    document.head.appendChild(style);
  }

  function createOverlay() {
    injectStyles();

    const host = document.getElementById('viewer-shell') || document.getElementById('game') || document.body;
    if (getComputedStyle(host).position === 'static') {
      host.style.position = 'relative';
    }

    overlay = document.createElement('aside');
    overlay.id = 'ram-overlay';
    overlay.setAttribute('aria-live', 'polite');
    overlay.setAttribute('aria-label', 'Game Boy RAM state overlay');
    host.appendChild(overlay);
  }

  function formatHex(value) {
    const number = Number(value) || 0;
    return `0x${number.toString(16).padStart(2, '0').toUpperCase()}`;
  }

  function formatParty(party) {
    if (!party || party.length === 0) {
      return '<div class="party"><div class="party-title">Party</div><span>empty / unavailable</span></div>';
    }

    const rows = party.map((mon) => {
      const hp = Number.isFinite(mon.hp) && Number.isFinite(mon.maxHp)
        ? ` HP ${mon.hp}/${mon.maxHp}`
        : '';
      const level = Number.isFinite(mon.level) && mon.level > 0 ? ` Lv${mon.level}` : '';
      const status = mon.status ? ` status:${formatHex(mon.status)}` : '';
      return `<li>${escapeHtml(mon.slot)}. ${escapeHtml(mon.name || `Species_${mon.speciesId}`)}${escapeHtml(level)}${escapeHtml(hp)}${escapeHtml(status)}</li>`;
    }).join('');

    return `<div class="party"><div class="party-title">Party</div><ul>${rows}</ul></div>`;
  }

  function render() {
    if (!overlay) {
      return;
    }

    const getState = global.getRAMState || (global.PokemonRAMBridge && global.PokemonRAMBridge.getRAMState);
    const state = typeof getState === 'function'
      ? getState()
      : { ramAvailable: false, source: 'demo', playerX: 0, playerY: 0, mapId: 0, mapName: 'unknown', screenType: 'unknown', party: [] };

    const badge = state.ramAvailable ? 'RAM' : 'DEMO';
    const note = state.raw && state.raw.note ? `<dd>${escapeHtml(state.raw.note)}</dd>` : '';

    overlay.innerHTML = `
      <div class="ram-title"><span>RAM State</span><span class="ram-badge">${badge}</span></div>
      <dl>
        <dt>Source</dt><dd>${escapeHtml(state.source || 'unknown')}</dd>
        <dt>Player</dt><dd>x=${escapeHtml(state.playerX)} y=${escapeHtml(state.playerY)}</dd>
        <dt>Map</dt><dd>${formatHex(state.mapId)} ${escapeHtml(state.mapName || '')}</dd>
        <dt>Screen</dt><dd>${escapeHtml(state.screenType || 'unknown')}</dd>
        ${note ? '<dt>Note</dt>' + note : ''}
      </dl>
      ${formatParty(state.party)}
    `;
  }

  function animationLoop(timestamp) {
    if (timestamp - lastRender >= UPDATE_INTERVAL_MS) {
      render();
      lastRender = timestamp;
    }
    global.requestAnimationFrame(animationLoop);
  }

  function setVisible(nextVisible) {
    visible = Boolean(nextVisible);
    if (overlay) {
      overlay.hidden = !visible;
    }

    const button = document.getElementById('toggle-overlay');
    if (button) {
      button.setAttribute('aria-pressed', String(visible));
      button.textContent = visible ? 'Hide Overlay' : 'Show Overlay';
    }
  }

  function toggleOverlay() {
    setVisible(!visible);
  }

  function bindControls() {
    const button = document.getElementById('toggle-overlay');
    if (button) {
      button.addEventListener('click', toggleOverlay);
    }

    document.addEventListener('keydown', (event) => {
      const target = event.target;
      const isTyping = target && (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable
      );

      if (!isTyping && event.key === '/') {
        event.preventDefault();
        toggleOverlay();
      }
    });
  }

  function init() {
    createOverlay();
    bindControls();
    setVisible(true);
    render();
    global.requestAnimationFrame(animationLoop);
  }

  global.toggleRAMOverlay = toggleOverlay;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})(window, document);
