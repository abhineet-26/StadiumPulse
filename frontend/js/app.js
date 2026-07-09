/**
 * StadiumPulse Fan Assistant Frontend Logic (v3.0)
 * Modernized with Tab Navigation and Ops Dashboard Integration.
 */

document.addEventListener('DOMContentLoaded', () => {
  // --- State ---
  let accessibilityMode = false;
  let isWaiting = false;

  // --- DOM Elements ---
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
  
  // Tabs
  const tabBtns = document.querySelectorAll('.tab-btn');
  const panels = document.querySelectorAll('.panel-view');

  // --- UI Interactions ---

  // Banner close
  document.getElementById('demo-banner-close').addEventListener('click', (e) => {
    e.target.parentElement.style.display = 'none';
    document.documentElement.style.setProperty('--banner-h', '0px');
  });

  // Tab Navigation Logic
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      // Deactivate all
      tabBtns.forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      panels.forEach(p => p.classList.remove('active'));

      // Activate clicked
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      const targetPanel = document.getElementById(btn.getAttribute('aria-controls'));
      targetPanel.classList.add('active');
      
      // Fetch fresh ops data immediately if Ops tab clicked
      if (btn.id === 'tab-ops') {
        fetchDensity();
      }
    });
  });

  // Countdown & Live Match Simulation
  const kickoff = new Date();
  kickoff.setHours(kickoff.getHours() + 2); // 2 hours from now
  kickoff.setMinutes(kickoff.getMinutes() + 30);
  
  setInterval(async () => {
    try {
      // Optional: Fetch live match state
      const res = await fetch('/api/match');
      if (res.ok) {
        const data = await res.json();
        document.getElementById('match-status').textContent = data.status;
        document.getElementById('match-minute').textContent = data.minute;
      }
    } catch (e) {
      // Fallback to local clock
      const now = new Date();
      const diff = Math.max(0, kickoff - now);
      const m = Math.floor((diff % 3600000) / 60000);
      document.getElementById('match-minute').textContent = String(m).padStart(2, '0');
    }
  }, 10000);

  // Poll Gate Density
  async function fetchDensity() {
    try {
      const res = await fetch('/api/density');
      if (res.ok) {
        const data = await res.json();
        
        // Update both Map Wait times and Ops Dashboard metrics
        ['A', 'C', 'E', 'G'].forEach(gate => {
          // Update Map
          const mapEl = document.getElementById(`wait-${gate}`);
          const mapRect = document.getElementById(`rect-wait-${gate}`);
          
          // Update Ops Dashboard
          const opsCard = document.getElementById(`metric-${gate}`);
          
          if (data[gate] !== undefined) {
            const waitStr = `${data[gate]}m`;
            
            if (mapEl) mapEl.textContent = waitStr;
            if (opsCard) opsCard.querySelector('.metric-value').textContent = waitStr;

            // Color code based on wait time
            let colorVar = 'var(--info)';
            let trendStr = 'Normal Flow';
            
            if (data[gate] > 30) {
              colorVar = 'var(--crit)';
              trendStr = 'Critical Surge';
            } else if (data[gate] > 20) {
              colorVar = 'var(--warn)';
              trendStr = 'Elevated';
            }
            
            if (mapRect) mapRect.setAttribute('fill', colorVar);
            if (opsCard) {
              opsCard.style.borderColor = colorVar;
              opsCard.querySelector('.metric-trend').textContent = trendStr;
              opsCard.querySelector('.metric-trend').style.color = colorVar;
            }
          }
        });
      }
    } catch (e) {
      console.warn("Could not fetch density:", e);
    }
  }
  fetchDensity();
  setInterval(fetchDensity, 10000); // Fast polling for demo

  // --- Chat Toggles ---
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

  // --- Chat Input & Forms ---
  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  });

  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isWaiting && chatInput.value.trim()) sendMessage();
    }
  });

  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      chatInput.value = chip.dataset.query;
      chatInput.style.height = 'auto';
      if (!isWaiting) sendMessage();
    });
  });

  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!isWaiting && chatInput.value.trim()) sendMessage();
  });

  // --- Message Rendering ---
  function renderMarkdown(text) {
    return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
               .replace(/\n/g, '<br>');
  }

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
        badges.innerHTML += `<span class="badge badge-conf-high">✓ Grounded</span>`;
        if (metaData.source) {
          badges.innerHTML += `<span class="badge badge-source">📚 ${metaData.source}</span>`;
        }
      }
      
      if (accessibilityMode) {
        badges.innerHTML += `<span class="badge badge-acc">♿ Acc. Mode</span>`;
      }

      meta.appendChild(badges);
      wrapper.appendChild(meta);
      
      // Add escalate button for fallback
      if (metaData.fallback) {
        const escalateBtn = document.createElement('button');
        escalateBtn.className = 'escalate-btn';
        escalateBtn.innerHTML = '🚨 Escalate to Staff';
        escalateBtn.onclick = () => {
          escalateBtn.disabled = true;
          escalateBtn.innerHTML = '✅ Command Center Notified';
          escalateBtn.style.background = 'rgba(0, 245, 160, 0.1)';
          escalateBtn.style.color = 'var(--safe)';
          escalateBtn.style.borderColor = 'var(--safe)';
          addSystemMessage("Ops Dashboard alerted. A volunteer has been dispatched to your location.");
        };
        wrapper.appendChild(escalateBtn);
      }
    }
    
    return wrapper;
  }

  function addSystemMessage(text) {
    const el = document.createElement('div');
    el.style.cssText = 'text-align:center; font-size:11px; color:var(--text-muted); padding:10px 0; font-weight:600; text-transform:uppercase;';
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

  // --- API Call ---
  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = '';
    chatInput.style.height = 'auto';
    chatInput.blur();
    isWaiting = true;
    sendBtn.disabled = true;

    chatMessages.appendChild(createMessageEl('user', text));
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    showTypingIndicator();

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
          throw new Error('Rate limit exceeded.');
        } else if (response.status === 422) {
          throw new Error('Invalid input format.');
        } else {
          throw new Error(`Server error (${response.status})`);
        }
      }

      const data = await response.json();
      chatMessages.appendChild(createMessageEl('ai', data.text, data));

    } catch (err) {
      removeTypingIndicator();
      const errorEl = createMessageEl('ai', `⚠️ **System Error:** ${err.message}`);
      errorEl.querySelector('.message-bubble').style.borderColor = 'var(--crit)';
      chatMessages.appendChild(errorEl);
    } finally {
      isWaiting = false;
      sendBtn.disabled = false;
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  }

  // --- Init Welcome ---
  const welcomes = {
    'en': "👋 **Welcome to StadiumPulse FIFA 26!**\n\nAsk me for directions, seat locations, accessible routes, or transit info.",
    'pt': "👋 **Bem-vindo ao StadiumPulse FIFA 26!**\n\nPergunte-me sobre direções, localização de assentos, rotas acessíveis ou transporte.",
    'es': "👋 **¡Bienvenido a StadiumPulse FIFA 26!**\n\nPregúntame sobre direcciones, ubicación de asientos, rutas accesibles o transporte."
  };
  
  chatMessages.appendChild(createMessageEl('ai', welcomes[langSelect.value]));

  langSelect.addEventListener('change', () => {
    if (chatMessages.children.length <= 1) { 
      chatMessages.innerHTML = '';
      chatMessages.appendChild(createMessageEl('ai', welcomes[langSelect.value]));
    }
  });

  // --- Staff Copilot Actions ---
  const btnTranslate = document.getElementById('btn-action-translate');
  const btnPolicy = document.getElementById('btn-action-policy');
  const btnMedical = document.getElementById('btn-action-medical');

  if (btnTranslate) {
    btnTranslate.addEventListener('click', () => {
      chatInput.value = 'Translate: Where are the bathrooms? (to Spanish)';
      document.getElementById('tab-fan').click();
      sendMessage();
    });
  }

  if (btnPolicy) {
    btnPolicy.addEventListener('click', () => {
      chatInput.value = 'What is the bag policy for backpacks?';
      document.getElementById('tab-fan').click();
      sendMessage();
    });
  }

  if (btnMedical) {
    btnMedical.addEventListener('click', () => {
      btnMedical.innerHTML = '<span class="action-icon">✅</span><h3>Dispatched</h3><p>EMS is en route</p>';
      btnMedical.style.background = 'rgba(255, 74, 74, 0.2)';
      alert('Medical incident reported to Command Center. EMS dispatched to your zone.');
    });
  }
});
