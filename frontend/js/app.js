/**
 * StadiumPulse Fan Assistant Frontend Logic (v2.0)
 * Connects to the FastAPI /api/chat endpoint.
 */

document.addEventListener('DOMContentLoaded', () => {
  // State
  let accessibilityMode = false;
  let isWaiting = false;

  // DOM Elements
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const chatMessages = document.getElementById('chat-messages');
  const langSelect = document.getElementById('lang-select');
  const btnAccess = document.getElementById('btn-access');
  const btnMap = document.getElementById('btn-map');
  const mapPanel = document.getElementById('map-panel');
  const sendBtn = document.getElementById('btn-send');
  const chips = document.querySelectorAll('.chip');
  const typingTmpl = document.getElementById('typing-tmpl');
  
  // Banner close
  document.getElementById('demo-banner-close').addEventListener('click', (e) => {
    e.target.parentElement.style.display = 'none';
    document.documentElement.style.setProperty('--banner-h', '0px');
  });

  // Countdown Timer Simulation
  const kickoff = new Date();
  kickoff.setHours(kickoff.getHours() + 2); // 2 hours from now
  kickoff.setMinutes(kickoff.getMinutes() + 30);
  
  setInterval(() => {
    const now = new Date();
    const diff = Math.max(0, kickoff - now);
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    document.getElementById('cd-hours').textContent = String(h).padStart(2, '0');
    document.getElementById('cd-minutes').textContent = String(m).padStart(2, '0');
  }, 1000);

  // Toggles
  btnAccess.addEventListener('click', () => {
    accessibilityMode = !accessibilityMode;
    btnAccess.setAttribute('aria-pressed', accessibilityMode);
    
    // Add system message indicating mode change
    const msg = accessibilityMode 
      ? '♿ Accessibility mode enabled. Routes will prioritize step-free access.'
      : 'Accessibility mode disabled. Standard routing restored.';
    addSystemMessage(msg);
  });

  btnMap.addEventListener('click', () => {
    const isVisible = mapPanel.classList.contains('hidden');
    if (isVisible) {
      mapPanel.classList.remove('hidden');
      btnMap.setAttribute('aria-pressed', 'true');
    } else {
      mapPanel.classList.add('hidden');
      btnMap.setAttribute('aria-pressed', 'false');
    }
  });

  // Textarea auto-resize and Enter key behavior
  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  });

  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isWaiting && chatInput.value.trim()) {
        sendMessage();
      }
    }
  });

  // Chips
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      chatInput.value = chip.dataset.query;
      chatInput.style.height = 'auto';
      if (!isWaiting) sendMessage();
    });
  });

  // Form submit
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!isWaiting && chatInput.value.trim()) {
      sendMessage();
    }
  });

  // Render markdown-lite (bolding)
  function renderMarkdown(text) {
    return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
               .replace(/\n/g, '<br>');
  }

  // Create message element
  function createMessageEl(role, text, metaData = null) {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${role}`;
    
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = renderMarkdown(text);
    wrapper.appendChild(bubble);

    if (metaData) {
      const meta = document.createElement('div');
      meta.className = 'message-meta';
      
      const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const timeSpan = document.createElement('span');
      timeSpan.textContent = time;
      meta.appendChild(timeSpan);
      
      const badges = document.createElement('div');
      badges.className = 'badge-row';
      
      if (metaData.fallback) {
        badges.innerHTML += `<span class="badge badge-conf-low">⚠ Fallback (No KB Match)</span>`;
      } else {
        badges.innerHTML += `<span class="badge badge-conf-high">✓ Grounded Response</span>`;
        if (metaData.source) {
          badges.innerHTML += `<span class="badge badge-source">📚 Source: ${metaData.source}</span>`;
        }
      }
      
      if (accessibilityMode) {
        badges.innerHTML += `<span class="badge badge-acc">♿ Acc. Mode</span>`;
      }

      meta.appendChild(badges);
      wrapper.appendChild(meta);
    }
    
    return wrapper;
  }

  function addSystemMessage(text) {
    const el = document.createElement('div');
    el.style.cssText = 'text-align:center; font-size:11px; color:var(--text-muted); padding:10px 0; font-weight:500;';
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
    const indicator = document.getElementById('typing-indicator');
    if (indicator) indicator.remove();
  }

  // API Call
  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    // UI state updates
    chatInput.value = '';
    chatInput.style.height = 'auto';
    chatInput.blur();
    isWaiting = true;
    sendBtn.disabled = true;

    // Add user message
    chatMessages.appendChild(createMessageEl('user', text));
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    showTypingIndicator();

    // Prepare payload
    const payload = {
      message: text,
      language: langSelect.value,
      accessibility_mode: accessibilityMode
    };

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      removeTypingIndicator();

      if (!response.ok) {
        if (response.status === 429) {
          throw new Error('Rate limit exceeded. Please wait a moment.');
        } else if (response.status === 422) {
          throw new Error('Message is too long or contains invalid characters.');
        } else {
          throw new Error(`Server error (${response.status})`);
        }
      }

      const data = await response.json();
      
      // Render AI response with metadata
      const aiMsg = createMessageEl('ai', data.text, data);
      chatMessages.appendChild(aiMsg);

    } catch (err) {
      removeTypingIndicator();
      const errorEl = createMessageEl('ai', `⚠️ **Error:** ${err.message}`);
      errorEl.querySelector('.message-bubble').style.borderColor = 'var(--crit)';
      chatMessages.appendChild(errorEl);
    } finally {
      isWaiting = false;
      sendBtn.disabled = false;
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  }

  // Welcome message based on initial language
  const welcomes = {
    'en': "👋 **Welcome to StadiumPulse!**\n\nI'm your Fan Assistant for today's match. Ask me for directions, seat locations, accessible routes, or transit info.",
    'pt': "👋 **Bem-vindo ao StadiumPulse!**\n\nSou seu Assistente de Fã para o jogo de hoje. Pergunte-me sobre direções, localização de assentos, rotas acessíveis ou informações de transporte.",
    'es': "👋 **¡Bienvenido a StadiumPulse!**\n\nSoy tu Asistente para el partido de hoy. Pregúntame sobre direcciones, ubicación de asientos, rutas accesibles o información de transporte."
  };
  
  const initialLang = langSelect.value;
  chatMessages.appendChild(createMessageEl('ai', welcomes[initialLang]));

  // Change welcome language if user changes dropdown before chatting
  langSelect.addEventListener('change', () => {
    if (chatMessages.children.length <= 1) { // Only the welcome message is there
      chatMessages.innerHTML = '';
      chatMessages.appendChild(createMessageEl('ai', welcomes[langSelect.value]));
    }
  });

});
