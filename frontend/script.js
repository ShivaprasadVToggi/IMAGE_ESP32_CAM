/**
 * ESP32-CAM Security Stream Portal — Client Script v2
 * Zero-Latency Edition
 *
 * CRITICAL ANTI-CACHE MEASURES:
 *  - fetch() with cache: 'no-store' header
 *  - Cache-busting timestamp query parameter on every request
 *  - Prevents the browser from ever serving a stale frame
 *
 * Features:
 *  - 200ms polling loop
 *  - FPS counter & round-trip latency tracking
 *  - Smooth online/offline state transitions
 *  - Live viewport timestamp overlay
 */

// ═══════════════════════════════════════════════════════════════
// ▸ CONFIGURATION
// ═══════════════════════════════════════════════════════════════
const RELAY_URL = 'https://image-esp32-cam.onrender.com';
const POLL_INTERVAL_MS = 200;
// ═══════════════════════════════════════════════════════════════

// ─── DOM Elements ─────────────────────────────────────────────
const feedImage       = document.getElementById('feed-image');
const offlinePlaceholder = document.getElementById('offline-placeholder');
const streamContainer = document.getElementById('stream-container');
const systemBadge     = document.getElementById('badge-system');
const systemBadgeDot  = document.getElementById('badge-system-dot');
const systemBadgeText = document.getElementById('badge-system-text');
const recIndicator    = document.getElementById('rec-indicator');
const camLabel        = document.getElementById('cam-label');
const headerTimeText  = document.getElementById('header-time-text');
const viewportTime    = document.getElementById('viewport-time');
const viewportDate    = document.getElementById('viewport-date');
const statFrames      = document.getElementById('stat-frames');
const statStatus      = document.getElementById('stat-status');
const statLatency     = document.getElementById('stat-latency-val');
const streamFps       = document.getElementById('stream-fps');

// ─── State ────────────────────────────────────────────────────
let frameCount = 0;
let isOnline   = false;
let pollTimer  = null;

// FPS calculation
let fpsFrameCount  = 0;
let fpsLastUpdate  = performance.now();
let currentFps     = 0;

// ─── Clock ────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();

  // Header clock
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
  headerTimeText.textContent = `${dateStr} — ${timeStr}`;

  // Viewport overlay clock
  viewportTime.textContent = timeStr;
  viewportDate.textContent = now.toISOString().split('T')[0];
}

// ─── FPS Tracker ──────────────────────────────────────────────
function updateFps() {
  const now = performance.now();
  const delta = now - fpsLastUpdate;

  if (delta >= 1000) {
    currentFps = Math.round((fpsFrameCount / delta) * 1000);
    fpsFrameCount = 0;
    fpsLastUpdate = now;
    streamFps.textContent = `${currentFps} FPS`;
  }
}

// ─── Set Online State ─────────────────────────────────────────
function setOnline(base64Image) {
  // Transition from offline → online
  if (!isOnline) {
    isOnline = true;

    streamContainer.classList.add('online');
    streamContainer.classList.remove('offline');

    systemBadge.classList.add('badge--online');
    systemBadge.classList.remove('badge--offline');
    systemBadgeText.textContent = '● System Online (Live)';

    recIndicator.classList.remove('hidden');
    camLabel.textContent = 'Live Secure Feed';

    offlinePlaceholder.classList.add('hidden');
    feedImage.style.opacity = '1';
  }

  // Update frame — direct base64 binding
  feedImage.src = 'data:image/jpeg;base64,' + base64Image;
  frameCount++;
  fpsFrameCount++;

  // Update stats
  statFrames.innerHTML = `FRAMES <span class="value green">${frameCount.toLocaleString()}</span>`;
  statStatus.innerHTML = `STATUS <span class="value green">RECEIVING</span>`;

  updateFps();
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

    recIndicator.classList.add('hidden');
    camLabel.textContent = 'CAM-01 • Disconnected';

    offlinePlaceholder.classList.remove('hidden');
    feedImage.style.opacity = '0';

    statStatus.innerHTML = `STATUS <span class="value red">NO SIGNAL</span>`;
    streamFps.textContent = '-- FPS';
    statLatency.textContent = '--';
    statLatency.className = 'value';

    // Reset FPS counter
    fpsFrameCount = 0;
    currentFps = 0;
  }
}

// ─── Poll Relay Server (Zero-Cache) ──────────────────────────
async function pollFrame() {
  const fetchStart = performance.now();

  try {
    // CRITICAL: Cache-busting via both fetch options AND a unique query param
    // This prevents browsers, CDNs, and service workers from serving stale data
    const cacheBuster = Date.now();
    const response = await fetch(`${RELAY_URL}/latest-frame?t=${cacheBuster}`, {
      cache: 'no-store',
      headers: {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
      }
    });

    if (!response.ok) {
      setOffline();
      return;
    }

    const data = await response.json();

    // Measure round-trip latency
    const latencyMs = Math.round(performance.now() - fetchStart);
    if (latencyMs < 200) {
      statLatency.textContent = `${latencyMs}ms`;
      statLatency.className = 'value green';
    } else if (latencyMs < 500) {
      statLatency.textContent = `${latencyMs}ms`;
      statLatency.className = 'value cyan';
    } else {
      statLatency.textContent = `${latencyMs}ms`;
      statLatency.className = 'value red';
    }

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

  // Start in offline state
  setOffline();

  // Begin polling
  pollTimer = setInterval(pollFrame, POLL_INTERVAL_MS);

  // Console branding
  console.log(
    '%c🛡️ Security Stream Portal v2.0 (Zero-Latency)',
    'color: #2ea44f; font-weight: bold; font-size: 16px;'
  );
  console.log(
    '%c   Relay:    ' + RELAY_URL +
    '\n   Polling:  ' + POLL_INTERVAL_MS + 'ms' +
    '\n   Cache:    DISABLED (no-store + timestamp bust)',
    'color: #8b949e; font-size: 11px; font-family: monospace;'
  );
}

// ─── Boot ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
