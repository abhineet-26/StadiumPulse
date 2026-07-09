/**
 * StadiumPulse Fan Assistant — Frontend Logic (v3.0)
 * FIFA World Cup 2026 Edition
 *
 * Features:
 *  - Particle confetti on load
 *  - Live countdown (h:m:s)
 *  - Gate density polling + animated bar charts
 *  - Accessibility toggle with ARIA
 *  - Multilingual welcome messages
 *  - Markdown-lite rendering with XSS sanitization
 *  - Rate-limit + error handling with FIFA-themed messages
 */

'use strict';

document.addEventListener('DOMContentLoaded', () => {

  /* ─── State ─────────────────────────────────────────────── */
  let accessibilityMode = false;
  let isWaiting = false;
  const MAX_WAIT_MINS = 40; // for bar chart scaling

  /* ─── DOM ───────────────────────────────────────────────── */
  const chatForm      = document.getElementById('chat-form');
  const chatInput     = document.getElementById('chat-input');
  const chatMessages  = document.getElementById('chat-messages');
  const langSelect    = document.getElementById('lang-select');
  const btnAccess     = document.getElementById('btn-access');
  const btnMap        = document.getElementById('btn-map');
  const mapPanel      = document.getElementById('map-panel');
  const sendBtn       = document.getElementById('btn-send');
  const typingTmpl    = document.getElementById('typing-tmpl');

  /* ─── Banner Dismiss ─────────────────────────────────────── */
  const bannerClose = document.getElementById('demo-banner-close');
  if (bannerClose) {
    bannerClose.addEventListener('click', () => {
      const banner = document.getElementById('demo-banner');
      if (banner) banner.remove();
    });
  }

  /* ─── Particle System ───────────────────────────────────── */
  (function initParticles() {
    const canvas = document.getElementById('particle-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let particles = [];
    let animId = null;

    function resize() {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    function spawnBurst(count) {
      for (let i = 0; i < count; i++) {
        particles.push({
          x: Math.random() * canvas.width,
          y: -10,
          vx: (Math.random() - 0.5) * 2,
          vy: Math.random() * 2 + 1,
          size: Math.random() * 4 + 2,
          color: ['#FFD700','#00FF87','#E8002D','#3B82F6','#ffffff'][Math.floor(Math.random() * 5)],
          life: 1.0,
          decay: Math.random() * 0.008 + 0.004,
          rotation: Math.random() * 360,
          rotSpeed: (Math.random() - 0.5) * 4,
        });
      }
    }

    function loop() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles = particles.filter(p => p.life > 0);
      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy; p.vy += 0.03;
        p.rotation += p.rotSpeed; p.life -= p.decay;
        ctx.save();
        ctx.globalAlpha = Math.max(0, p.life);
        ctx.fillStyle = p.color;
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
        ctx.restore();
      });
      animId = requestAnimationFrame(loop);
      if (particles.length === 0 && animId) {
        cancelAnimationFrame(animId); animId = null;
      }
    }

    // Burst on load
    spawnBurst(80);
    loop();

    // Expose for reuse
    window._spawnParticles = spawnBurst;
  })();

  /* ─── Countdown Timer ───────────────────────────────────── */
  const kickoff = new Date(Date.now() + 2.5 * 3600 * 1000); // 2h30m from now

  function updateCountdown() {
    const diff = Math.max(0, kickoff - Date.now());
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    const hours   = document.getElementById('cd-hours');
    const minutes = document.getElementById('cd-minutes');
    const seconds = document.getElementById('cd-seconds');
    if (hours)   hours.textContent   = String(h).padStart(2, '0');
    if (minutes) minutes.textContent = String(m).padStart(2, '0');
    if (seconds) seconds.textContent = String(s).padStart(2, '0');
  }
  updateCountdown();
  setInterval(updateCountdown, 1000);

  /* ─── Gate Density Polling ──────────────────────────────── */
  const GATE_IDS = ['A', 'B', 'C', 'D', 'E', 'G'];

  /**
   * Returns color class based on wait minutes.
   * @param {number} mins
   * @returns {string} CSS color variable
   */
  function waitColor(mins) {
    if (mins > 30) return 'var(--crit)';
    if (mins > 20) return 'var(--warn)';
    return 'var(--safe)';
  }

  /**
   * Update gate markers on SVG map.
   * @param {string} gate
   * @param {number} mins
   */
  function updateMapGate(gate, mins) {
    const waitEl = document.getElementById(`wait-${gate}`);
    const bgEl   = document.getElementById(`wait-bg-${gate}`);
    if (waitEl) waitEl.textContent = `${mins}m`;
    if (bgEl) {
      const color = mins > 30 ? '#E8002D' : mins > 20 ? '#FFB020' : '#3B82F6';
      bgEl.setAttribute('fill', color);
    }
  }

  /**
   * Update gate density card.
   * @param {string} gate
   * @param {number} mins
   */
  function updateCard(gate, mins) {
    const waitEl = document.getElementById(`card-wait-${gate}`);
    const barEl  = document.getElementById(`bar-${gate}`);
    if (waitEl) {
      waitEl.textContent = `${mins}m`;
      waitEl.style.color = waitColor(mins);
    }
    if (barEl) {
      const pct = Math.min(100, (mins / MAX_WAIT_MINS) * 100);
      barEl.style.width = `${pct}%`;
      barEl.style.background = waitColor(mins);
    }
  }

  async function fetchDensity() {
    try {
      const res = await fetch('/api/density');
      if (!res.ok) return;
      const data = await res.json();
      GATE_IDS.forEach(gate => {
        const mins = data[gate];
        if (mins !== undefined) {
          updateMapGate(gate, mins);
          updateCard(gate, mins);
        }
      });
      const statusEl = document.getElementById('map-status-text');
      if (statusEl) {
        const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        statusEl.textContent = `Updated ${now}`;
      }
    } catch (err) {
      console.warn('[StadiumPulse] Gate density fetch failed:', err);
    }
  }
  fetchDensity();
  setInterval(fetchDensity, 30_000);

  /* ─── Control Toggles ───────────────────────────────────── */
  btnAccess.addEventListener('click', () => {
    accessibilityMode = !accessibilityMode;
    btnAccess.setAttribute('aria-pressed', String(accessibilityMode));
    btnAccess.classList.toggle('active', accessibilityMode);
    const msg = accessibilityMode
      ? '♿ Accessibility mode ON — routes will prioritise step-free access.'
      : 'Accessibility mode OFF — standard routing restored.';
    addSystemMessage(msg);
  });

  btnMap.addEventListener('click', () => {
    const visible = !mapPanel.classList.contains('hidden');
    mapPanel.classList.toggle('hidden', visible);
    btnMap.setAttribute('aria-pressed', String(!visible));
    btnMap.classList.toggle('active', !visible);
  });

  /* ─── Textarea Auto-resize ──────────────────────────────── */
  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  });

  chatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isWaiting && chatInput.value.trim()) sendMessage();
    }
  });

  /* ─── Chips ─────────────────────────────────────────────── */
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      chatInput.value = chip.dataset.query;
      chatInput.style.height = 'auto';
      if (!isWaiting) sendMessage();
    });
  });

  /* ─── Form Submit ───────────────────────────────────────── */
  chatForm.addEventListener('submit', e => {
    e.preventDefault();
    if (!isWaiting && chatInput.value.trim()) sendMessage();
  });

  /* ─── Markdown Renderer (safe) ──────────────────────────── */
  /**
   * Renders a limited subset of markdown to HTML.
   * No user-provided HTML is interpolated directly.
   * @param {string} text — plain text with **bold** and newlines
   * @returns {string} safe HTML string
   */
  function renderMarkdown(text) {
    // Escape HTML first to prevent XSS
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
    // Then apply safe markdown transforms
    return escaped
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }

  /* ─── Message Element Factory ───────────────────────────── */
  /**
   * @param {'user'|'ai'} role
   * @param {string} text
   * @param {object|null} meta — ChatResponse fields
   * @returns {HTMLElement}
   */
  function createMessageEl(role, text, meta = null) {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${role}`;

    // Avatar (AI only)
    if (role === 'ai') {
      const avatar = document.createElement('div');
      avatar.className = 'msg-avatar';
      avatar.setAttribute('aria-hidden', 'true');
      avatar.textContent = '⚽';
      wrapper.appendChild(avatar);
    }

    const content = document.createElement('div');
    content.className = 'message-content';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = renderMarkdown(text);
    content.appendChild(bubble);

    if (meta) {
      const metaEl = document.createElement('div');
      metaEl.className = 'message-meta';

      const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const timeSpan = document.createElement('span');
      timeSpan.textContent = time;
      metaEl.appendChild(timeSpan);

      const badges = document.createElement('div');
      badges.className = 'badge-row';

      if (meta.fallback) {
        badges.innerHTML = '<span class="badge badge-conf-low">⚠ No KB Match</span>';
      } else {
        badges.innerHTML = '<span class="badge badge-conf-high">✓ Grounded</span>';
        if (meta.source) {
          badges.innerHTML += `<span class="badge badge-source">📚 ${escapeHtml(meta.source)}</span>`;
        }
      }
      if (accessibilityMode) {
        badges.innerHTML += '<span class="badge badge-acc">♿ Acc. Mode</span>';
      }

      metaEl.appendChild(badges);
      content.appendChild(metaEl);

      if (meta.fallback) {
        const btn = document.createElement('button');
        btn.className = 'escalate-btn';
        btn.innerHTML = '🚨 Escalate to Staff';
        btn.setAttribute('aria-label', 'Escalate to stadium staff for help');
        btn.addEventListener('click', () => {
          btn.disabled = true;
          btn.innerHTML = '✅ Staff Notified';
          btn.style.cssText = 'background:rgba(0,255,135,0.08);color:var(--safe);border-color:var(--safe);cursor:default;';
          addSystemMessage('🟢 Ops Dashboard alerted. A volunteer is on their way to assist you.');
          if (window._spawnParticles) window._spawnParticles(20);
        });
        content.appendChild(btn);
      }
    }

    wrapper.appendChild(content);
    return wrapper;
  }

  /**
   * Minimal HTML escaping for badge content.
   * @param {string} str
   * @returns {string}
   */
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function addSystemMessage(text) {
    const el = document.createElement('div');
    el.className = 'system-msg';
    el.textContent = text;
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function showTypingIndicator() {
    const clone = typingTmpl.content.cloneNode(true);
    chatMessages.appendChild(clone);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function removeTypingIndicator() {
    document.getElementById('typing-indicator')?.remove();
  }

  /* ─── Send Message ──────────────────────────────────────── */
  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text || isWaiting) return;

    chatInput.value = '';
    chatInput.style.height = 'auto';
    isWaiting = true;
    sendBtn.disabled = true;

    chatMessages.appendChild(createMessageEl('user', text));
    chatMessages.scrollTop = chatMessages.scrollHeight;
    showTypingIndicator();

    const payload = {
      message: text,
      language: langSelect.value,
      accessibility_mode: accessibilityMode,
    };

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      removeTypingIndicator();

      if (!res.ok) {
        const msgs = {
          429: '⏱️ Too many requests — please wait a moment before asking again.',
          422: '❌ Message is too long or contains invalid characters (max 500).',
        };
        throw new Error(msgs[res.status] ?? `Server error (${res.status}).`);
      }

      const data = await res.json();
      chatMessages.appendChild(createMessageEl('ai', data.text, data));
      if (data.confidence === 'high' && window._spawnParticles) {
        window._spawnParticles(15);
      }

    } catch (err) {
      removeTypingIndicator();
      const errEl = createMessageEl('ai', `⚠️ **Oops!** ${err.message}`);
      errEl.querySelector('.message-bubble').style.borderColor = 'var(--crit)';
      chatMessages.appendChild(errEl);
    } finally {
      isWaiting = false;
      sendBtn.disabled = false;
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  }

  /* ─── Welcome Messages ──────────────────────────────────── */
  const WELCOMES = {
    en: "👋 **Welcome to StadiumPulse!**\n\nYour AI-powered guide for **FIFA World Cup 2026** at MetLife Stadium. Ask me about gate directions, seat locations, accessible routes, transit, or venue policies.",
    pt: "👋 **Bem-vindo ao StadiumPulse!**\n\nSeu guia de IA para a **Copa do Mundo FIFA 2026** no MetLife Stadium. Pergunte sobre portões, assentos, rotas acessíveis ou transporte.",
    es: "👋 **¡Bienvenido a StadiumPulse!**\n\nTu asistente de IA para la **Copa del Mundo FIFA 2026** en MetLife Stadium. Pregúntame sobre puertas, asientos, rutas accesibles o transporte.",
  };

  function showWelcome(lang) {
    chatMessages.innerHTML = '';
    chatMessages.appendChild(createMessageEl('ai', WELCOMES[lang] ?? WELCOMES.en));
  }

  showWelcome(langSelect.value);

  langSelect.addEventListener('change', () => {
    if (chatMessages.querySelectorAll('.message.user').length === 0) {
      showWelcome(langSelect.value);
    }
  });

});
