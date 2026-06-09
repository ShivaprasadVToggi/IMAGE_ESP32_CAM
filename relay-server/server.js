/**
 * ESP32-CAM Cloud Relay Server — Zero-Latency Edition
 *
 * A lightweight Express server acting as an in-memory frame broker.
 * Designed to prevent the Cache Trap with aggressive no-cache headers
 * on every response.
 *
 * Routes:
 *   POST /upload        — Receives base64 JPEG frames from the publisher
 *   GET  /latest-frame  — Serves the freshest frame (4s timeout, NO CACHING)
 *   GET  /health        — Health check endpoint
 */

const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3001;

// ─── Middleware ───────────────────────────────────────────────
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// ─── In-Memory Frame Store ───────────────────────────────────
let latestFrame = null;
let lastUpdateTime = 0;

// ─── Constants ───────────────────────────────────────────────
const OFFLINE_THRESHOLD_MS = 4000; // 4 seconds

// ─── Routes ──────────────────────────────────────────────────

/**
 * POST /upload
 * Expects JSON: { "image": "base64_encoded_jpeg_string" }
 * Stores the frame in memory with a fresh timestamp.
 */
app.post('/upload', (req, res) => {
  const { image } = req.body;

  if (!image) {
    return res.status(400).json({ error: 'Missing "image" field in request body' });
  }

  latestFrame = image;
  lastUpdateTime = Date.now();

  return res.status(200).json({ status: 'ok', timestamp: lastUpdateTime });
});

/**
 * GET /latest-frame
 *
 * CRITICAL: Aggressive no-cache headers to prevent the Cache Trap.
 * Without these, browsers, CDNs, and Vercel's edge network will serve
 * stale frozen frames instead of live data.
 *
 * Returns the latest frame if received within the last 4 seconds,
 * otherwise returns offline status.
 */
app.get('/latest-frame', (req, res) => {
  // ── CACHE BUSTING — The most important 3 lines in this server ──
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  res.setHeader('Pragma', 'no-cache');
  res.setHeader('Expires', '0');
  // ───────────────────────────────────────────────────────────────

  const elapsed = Date.now() - lastUpdateTime;

  if (latestFrame && elapsed < OFFLINE_THRESHOLD_MS) {
    return res.status(200).json({
      status: 'online',
      image: latestFrame
    });
  }

  return res.status(200).json({ status: 'offline' });
});

/**
 * GET /health
 * Simple health check for deployment platforms.
 */
app.get('/health', (req, res) => {
  res.setHeader('Cache-Control', 'no-store');

  res.status(200).json({
    status: 'healthy',
    uptime: process.uptime(),
    frameBuffered: latestFrame !== null,
    lastFrameAge: latestFrame ? Date.now() - lastUpdateTime : null
  });
});

// ─── Start Server ────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n🛰️  ESP32-CAM Relay Server (Zero-Latency Edition)`);
  console.log(`   ├─ Status:   RUNNING`);
  console.log(`   ├─ Port:     ${PORT}`);
  console.log(`   ├─ Upload:   POST /upload`);
  console.log(`   ├─ Stream:   GET  /latest-frame  (NO-CACHE enforced)`);
  console.log(`   └─ Health:   GET  /health\n`);
});
