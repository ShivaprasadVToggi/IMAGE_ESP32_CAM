/**
 * ESP32-CAM Cloud Relay Server
 * 
 * A lightweight Express server that acts as an image buffer/broker
 * between the local Python publisher and the public Vercel dashboard.
 * 
 * Routes:
 *   POST /upload        — Receives base64 JPEG frames from the publisher
 *   GET  /latest-frame  — Serves the latest frame to the frontend (4s timeout)
 *   GET  /health        — Simple health check endpoint
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
let lastReceivedTimestamp = 0;

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
  lastReceivedTimestamp = Date.now();

  return res.status(200).json({ status: 'ok', timestamp: lastReceivedTimestamp });
});

/**
 * GET /latest-frame
 * Returns the latest frame if it was received within the last 4 seconds.
 * Otherwise, returns an offline status indicating the publisher is disconnected.
 */
app.get('/latest-frame', (req, res) => {
  const elapsed = Date.now() - lastReceivedTimestamp;

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
  res.status(200).json({
    status: 'healthy',
    uptime: process.uptime(),
    frameBuffered: latestFrame !== null,
    lastFrameAge: latestFrame ? Date.now() - lastReceivedTimestamp : null
  });
});

// ─── Start Server ────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n🛰️  ESP32-CAM Relay Server`);
  console.log(`   ├─ Status:  RUNNING`);
  console.log(`   ├─ Port:    ${PORT}`);
  console.log(`   ├─ Upload:  POST /upload`);
  console.log(`   ├─ Stream:  GET  /latest-frame`);
  console.log(`   └─ Health:  GET  /health\n`);
});
