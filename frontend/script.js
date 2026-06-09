/**
 * ESP32-CAM Security Stream Portal — Client Script
 *
 * Polls the relay server every 200ms for the latest frame,
 * updates the UI between online/offline states dynamically.
 */

// ═══════════════════════════════════════════════════════════════
// ▸ CONFIGURATION — Update this URL after deploying the relay!
// ═══════════════════════════════════════════════════════════════
const RELAY_URL = 'https://image-esp32-cam.onrender.com';
// Example: 'https://esp32-relay.onrender.com'
// For local testing: 'http://localhost:3001'
// ═══════════════════════════════════════════════════════════════

const POLL_INTERVAL_MS = 200;

// ─── DOM Elements ─────────────────────────────────────────────
const feedImage = document.getElementById('feed-image');
const offlinePlaceholder = document.getElementById('offline-placeholder');
const streamContainer = document.getElementById('stream-container');
const systemBadge = document.getElementById('badge-system');
const systemBadgeDot = document.getElementById('badge-system-dot');
const systemBadgeText = document.getElementById('badge-system-text');
const recDot = document.getElementById('rec-dot');
const camLabel = document.getElementById('cam-label');
const statFrames = document.getElementById('stat-frames');
const statStatus = document.getElementById('stat-status');
const statResolution = document.getElementById('stat-resolution');
const headerTime = document.getElementById('header-time');

// ─── State ────────────────────────────────────────────────────
let frameCount = 0;
let isOnline = false;
let pollTimer = null;

// ─── Clock ────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit'
  });
  const timeStr = now.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
  headerTime.textContent = `${dateStr} — ${timeStr}`;
}

// ─── Set Online State ─────────────────────────────────────────
function setOnline(base64Image) {
  if (!isOnline) {
    isOnline = true;
    streamContainer.classList.add('online');
    streamContainer.classList.remove('offline');
    systemBadge.classList.add('badge--online');
    systemBadge.classList.remove('badge--offline');
    systemBadgeDot.style.background = '';
    systemBadgeText.textContent = 'System Online (Live)';
    recDot.classList.remove('hidden');
    camLabel.textContent = 'CAM-01 • LIVE';
    offlinePlaceholder.classList.add('hidden');
    feedImage.style.opacity = '1';
  }

  feedImage.src = 'data:image/jpeg;base64,' + base64Image;
  frameCount++;

  statFrames.innerHTML = `FRAMES: <span class="value green">${frameCount}</span>`;
  statStatus.innerHTML = `STATUS: <span class="value green">RECEIVING</span>`;
}

// ─── Set Offline State ────────────────────────────────────────
function setOffline() {
  if (isOnline || frameCount === 0) {
    isOnline = false;
    streamContainer.classList.remove('online');
    streamContainer.classList.add('offline');
    systemBadge.classList.remove('badge--online');
    systemBadge.classList.add('badge--offline');
    systemBadgeText.textContent = 'Status: Offline';
    recDot.classList.add('hidden');
    camLabel.textContent = 'CAM-01 • DISCONNECTED';
    offlinePlaceholder.classList.remove('hidden');
    feedImage.style.opacity = '0';

    statStatus.innerHTML = `STATUS: <span class="value red">NO SIGNAL</span>`;
  }
}

// ─── Poll Relay Server ────────────────────────────────────────
async function pollFrame() {
  try {
    const response = await fetch(`${RELAY_URL}/latest-frame`, {
      cache: 'no-store'
    });

    if (!response.ok) {
      setOffline();
      return;
    }

    const data = await response.json();

    if (data.status === 'online' && data.image) {
      setOnline(data.image);
    } else {
      setOffline();
    }
  } catch (err) {
    // Network error — relay is unreachable
    setOffline();
  }
}

// ─── Initialize ───────────────────────────────────────────────
function init() {
  // Start clock
  updateClock();
  setInterval(updateClock, 1000);

  // Initial state
  setOffline();

  // Start polling
  pollTimer = setInterval(pollFrame, POLL_INTERVAL_MS);

  console.log(
    '%c🛡️ Security Stream Portal Initialized',
    'color: #2ea44f; font-weight: bold; font-size: 14px;'
  );
  console.log(
    `%c   Relay: ${RELAY_URL}\n   Poll:  ${POLL_INTERVAL_MS}ms`,
    'color: #8b949e; font-size: 11px;'
  );
}

// Boot
document.addEventListener('DOMContentLoaded', init);
