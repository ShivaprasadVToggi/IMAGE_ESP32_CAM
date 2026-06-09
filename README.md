# 🛡️ Cloud-Relayed Security Surveillance System

A real-time, zero-latency security surveillance pipeline that streams live ESP32-CAM footage through a cloud relay to a public web dashboard — accessible from any phone or browser, anywhere in the world.

![Architecture](https://img.shields.io/badge/Architecture-Cloud%20Relay-0d1117?style=for-the-badge&labelColor=161b22)
![Node.js](https://img.shields.io/badge/Node.js-Express-2ea44f?style=for-the-badge&logo=node.js&logoColor=white)
![Python](https://img.shields.io/badge/Python-OpenCV-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Vercel](https://img.shields.io/badge/Deployed-Vercel-000?style=for-the-badge&logo=vercel)
![Render](https://img.shields.io/badge/Relay-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)

---

## 📡 System Architecture

```
┌─────────────┐    USB Serial     ┌──────────────────┐    HTTP POST     ┌─────────────────┐    GET /latest    ┌──────────────────┐
│  ESP32-CAM   │ ──────────────► │   publisher.py    │ ──────────────► │   Relay Server   │ ◄────────────── │  Web Dashboard   │
│  (QQVGA)     │   0xAA 0xBB +   │  (Local Laptop)   │   Base64 JPEG   │  (Render Cloud)  │   200ms poll    │  (Vercel CDN)    │
│  160×120     │   Raw JPEG       │  OpenCV + Haar    │   Async Thread  │  Express.js      │   No-Cache      │  Dark Mode UI    │
└─────────────┘                   └──────────────────┘                  └─────────────────┘                  └──────────────────┘
                                         │                                                                          │
                                   Face Detection                                                              📱 Mobile
                                   Green Bounding Box                                                          💻 Desktop
                                   480×360 Upscale                                                             🌍 Anywhere
```

---

## 🗂️ Project Structure

```
IMAGE_ESP32_CAM/
├── relay-server/                 # Part A — Cloud Relay Backend
│   ├── server.js                 # Express server (POST /upload, GET /latest-frame)
│   ├── package.json              # Dependencies: express, cors
│   └── .gitignore
│
├── frontend/                     # Part B — Public Web Dashboard
│   ├── index.html                # Semantic HTML5 with tactical overlays
│   ├── style.css                 # Dark surveillance theme (580+ lines)
│   ├── script.js                 # 200ms polling loop with cache busting
│   └── vercel.json               # Static deploy config with no-cache headers
│
└── publisher.py                  # Part C — Local Laptop Publisher
```

---

## ⚡ Zero-Latency Design

This system is specifically engineered to prevent two critical real-time traps:

### 🔴 The Latency Trap
> **Problem:** Standard blocking HTTP uploads take ~200ms per round-trip. During that wait, the serial port buffer fills with stale frames, causing a growing delay that makes the feed show "old" footage.

| Solution | Location |
|----------|----------|
| `ser.reset_input_buffer()` at the start of every loop — discards stale serial data | `publisher.py` |
| Async uploads via `threading.Thread` — serial reading never blocks | `publisher.py` |
| Frame skipping — if previous upload still in flight, drop the current frame | `publisher.py` |

### 🔴 The Cache Trap
> **Problem:** Browsers, CDNs, and cloud platforms automatically cache responses. This causes the dashboard to display a frozen "cached" frame instead of the newest live frame.

| Layer | Solution | Location |
|-------|----------|----------|
| Server | `Cache-Control: no-store, no-cache, must-revalidate, proxy-revalidate` | `server.js` |
| Browser | `fetch()` with `cache: 'no-store'` + `?t=timestamp` query param | `script.js` |
| CDN | No-cache headers on all Vercel routes | `vercel.json` |
| HTML | `http-equiv` meta tags as backup | `index.html` |

---

## 🚀 Deployment Guide

### Prerequisites

- [Node.js](https://nodejs.org/) v18+
- [Python](https://python.org/) 3.8+ with pip
- A [Render](https://render.com/) account (free tier works)
- A [Vercel](https://vercel.com/) account (free tier works)
- A GitHub repository

### Step 1: Deploy the Relay Server → Render

1. Push this repository to GitHub.
2. Go to [render.com](https://render.com) → **New** → **Web Service**.
3. Connect your GitHub repo and configure:
   | Setting | Value |
   |---------|-------|
   | **Root Directory** | `relay-server` |
   | **Build Command** | `npm install` |
   | **Start Command** | `npm start` |
   | **Instance Type** | Free |
4. Deploy and note your URL (e.g., `https://image-esp32-cam.onrender.com`).

### Step 2: Deploy the Dashboard → Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project**.
2. Import your GitHub repo and configure:
   | Setting | Value |
   |---------|-------|
   | **Root Directory** | `frontend` |
   | **Framework Preset** | Other |
3. **Before deploying**, verify that `RELAY_URL` in `frontend/script.js` matches your Render URL:
   ```javascript
   const RELAY_URL = 'https://image-esp32-cam.onrender.com';
   ```
4. Deploy.

### Step 3: Run the Publisher → Local Laptop

1. Install Python dependencies:
   ```bash
   pip install pyserial opencv-python requests numpy
   ```
2. Verify `RELAY_URL` in `publisher.py` matches your Render URL:
   ```python
   RELAY_URL = "https://image-esp32-cam.onrender.com/upload"
   ```
3. Verify `SERIAL_PORT` matches your ESP32-CAM's port (default: `COM9`).
4. Connect the ESP32-CAM via USB and run:
   ```bash
   python publisher.py
   ```

---

## 🖥️ API Reference

### `POST /upload`

Receives a processed frame from the publisher.

```json
// Request Body
{ "image": "base64_encoded_jpeg_string" }

// Response (200 OK)
{ "status": "ok", "timestamp": 1781040158326 }
```

### `GET /latest-frame`

Returns the most recent frame if it was received within the last 4 seconds.

```json
// Response — Camera Online
{ "status": "online", "image": "base64_encoded_jpeg_string" }

// Response — Camera Offline (>4s since last frame)
{ "status": "offline" }
```

**Response Headers (Anti-Cache):**
```
Cache-Control: no-store, no-cache, must-revalidate, proxy-revalidate
Pragma: no-cache
Expires: 0
```

### `GET /health`

Health check for monitoring.

```json
{
  "status": "healthy",
  "uptime": 3600.5,
  "frameBuffered": true,
  "lastFrameAge": 150
}
```

---

## 🎨 Dashboard Features

| Feature | Description |
|---------|-------------|
| 🟢 **Glowing Status Badge** | Neon-green pulse animation when ONLINE, solid red when OFFLINE |
| 🔴 **REC Indicator** | Pulsing red dot + "REC" label during live feed |
| 📐 **Corner Brackets** | 4 green tactical brackets with breathing glow around the viewport |
| 📺 **Scanline Overlay** | Diagonal lines + horizontal sweep beam for surveillance aesthetic |
| 🕐 **Live Clock** | Real-time HH:MM:SS in header + timestamp overlay on the video |
| 📊 **Stats Bar** | Frame counter, connection status, round-trip latency, resolution |
| 📈 **FPS Counter** | Real-time frames-per-second measurement |
| 📱 **Responsive** | Optimized for mobile phones, tablets, and desktop browsers |
| 🌙 **Dark Theme** | `#0d1117` background with `#2ea44f` neon-green accents |

---

## 🔧 Configuration

### Serial Port (publisher.py)

```python
SERIAL_PORT = "COM9"        # Change to your ESP32-CAM's port
BAUD_RATE = 115200          # Must match ESP32-CAM firmware
OUTPUT_WIDTH = 480           # Upscaled resolution for face detection
OUTPUT_HEIGHT = 360
JPEG_QUALITY = 70            # Balance between quality and bandwidth
```

### Polling Rate (script.js)

```javascript
const POLL_INTERVAL_MS = 200;  // 200ms = ~5 FPS max polling rate
```

### Timeout Threshold (server.js)

```javascript
const OFFLINE_THRESHOLD_MS = 4000;  // 4 seconds before marking offline
```

---

## 📋 ESP32-CAM Serial Protocol

The ESP32-CAM firmware sends binary packets in this format:

```
┌──────────┬──────────────────┬─────────────────────┐
│ Sync     │ Size             │ Payload             │
│ 0xAA 0xBB│ 4 bytes (LE)     │ Raw JPEG (N bytes)  │
├──────────┼──────────────────┼─────────────────────┤
│ 2 bytes  │ 4 bytes          │ N bytes             │
└──────────┴──────────────────┴─────────────────────┘
```

- **Sync Header:** `0xAA 0xBB` — marks the start of a new frame
- **Size Field:** 4-byte unsigned little-endian integer — byte count of the JPEG payload
- **Payload:** Raw JPEG image data (typically 3–15 KB at QQVGA)

---

## 📄 License

This project is open-source. Built for educational and personal security monitoring purposes.

---

<p align="center">
  <b>Efficient Compression Pipeline | Developed for Low-Bandwidth Devices</b><br/>
  <sub>ESP32-CAM • OpenCV • Express.js • Vercel</sub>
</p>
