"""
ESP32-CAM Serial Publisher — Zero-Latency Edition
==================================================
Reads raw JPEG frames from an ESP32-CAM over USB serial,
performs local face detection using OpenCV Haar Cascades,
draws green bounding boxes, and uploads processed frames
to the cloud relay server.

CRITICAL ANTI-LATENCY MEASURES:
  1. Serial Buffer Purging: ser.reset_input_buffer() at the start
     of every loop iteration discards stale backed-up data so we
     only ever process the NEWEST live frame.
  2. Asynchronous Non-Blocking Uploads: HTTP POST runs in a
     background thread so the serial reading loop never blocks
     waiting for a 200ms+ network round-trip.
  3. Frame Skipping: If the previous upload thread is still active,
     we skip the current frame entirely to prevent backlog.

Protocol:
  [0xAA 0xBB] [4-byte LE size] [JPEG payload of `size` bytes]

Requirements:
  pip install pyserial opencv-python requests numpy
"""

import serial
import struct
import time
import base64
import sys
import threading

import cv2
import numpy as np
import requests

# ═══════════════════════════════════════════════════════════════
# ▸ CONFIGURATION — Update these before running
# ═══════════════════════════════════════════════════════════════
RELAY_URL = "https://image-esp32-cam.onrender.com/upload"
# For local testing: "http://localhost:3001/upload"

SERIAL_PORT = "COM9"
BAUD_RATE = 115200

# Output resolution for face detection and upload
OUTPUT_WIDTH = 480
OUTPUT_HEIGHT = 360

# JPEG encoding quality (0-100, lower = smaller file, faster upload)
JPEG_QUALITY = 70

# Face detection parameters
FACE_SCALE_FACTOR = 1.1
FACE_MIN_NEIGHBORS = 5
FACE_MIN_SIZE = (30, 30)

# Sync header bytes
SYNC_BYTE_1 = 0xAA
SYNC_BYTE_2 = 0xBB

# Frame size sanity bounds (bytes)
MIN_FRAME_SIZE = 1024       # 1 KB
MAX_FRAME_SIZE = 512000     # 500 KB

# Maximum consecutive errors before serial reset
MAX_CONSECUTIVE_ERRORS = 20
# ═══════════════════════════════════════════════════════════════


# ─── Shared State for Async Upload ────────────────────────────
upload_thread = None        # Reference to the active upload thread
upload_lock = threading.Lock()
frames_skipped = 0          # Counter for dropped frames


def load_face_cascade():
    """Load the Haar Cascade classifier for frontal face detection."""
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        print("[ERROR] Failed to load Haar Cascade from:", cascade_path)
        sys.exit(1)
    print(f"[INFO] Haar Cascade loaded: {cascade_path}")
    return cascade


def find_sync_header(ser):
    """
    Scan incoming serial bytes until we find the sync header 0xAA 0xBB.
    Returns True when found. Blocks until sync is detected.
    """
    while True:
        byte1 = ser.read(1)
        if len(byte1) == 0:
            continue
        if byte1[0] == SYNC_BYTE_1:
            byte2 = ser.read(1)
            if len(byte2) == 0:
                continue
            if byte2[0] == SYNC_BYTE_2:
                return True


def read_frame_payload(ser):
    """
    After sync header is found, read the 4-byte size field
    and then the JPEG payload.
    Returns raw JPEG bytes, or None on failure.
    """
    # Read 4-byte little-endian size
    size_bytes = ser.read(4)
    if len(size_bytes) < 4:
        print("[WARN] Incomplete size field, skipping frame")
        return None

    frame_size = struct.unpack('<I', size_bytes)[0]

    # Sanity check: reject suspicious sizes
    if frame_size < MIN_FRAME_SIZE or frame_size > MAX_FRAME_SIZE:
        print(f"[WARN] Suspicious frame size: {frame_size} bytes, skipping")
        return None

    # Read the JPEG payload in chunks
    jpeg_data = bytearray()
    remaining = frame_size
    while remaining > 0:
        chunk = ser.read(min(remaining, 4096))
        if len(chunk) == 0:
            print("[WARN] Serial read timeout during payload, skipping frame")
            return None
        jpeg_data.extend(chunk)
        remaining -= len(chunk)

    return bytes(jpeg_data)


def process_frame(jpeg_bytes, face_cascade):
    """
    Decode JPEG, resize, run face detection, draw bounding boxes,
    re-encode to compressed JPEG.
    Returns processed JPEG bytes, or None on failure.
    """
    # Decode the raw JPEG
    np_arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        print("[WARN] Failed to decode JPEG frame")
        return None

    # Resize to output resolution
    frame = cv2.resize(frame, (OUTPUT_WIDTH, OUTPUT_HEIGHT),
                       interpolation=cv2.INTER_LINEAR)

    # Face detection on grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=FACE_SCALE_FACTOR,
        minNeighbors=FACE_MIN_NEIGHBORS,
        minSize=FACE_MIN_SIZE
    )

    # Draw green bounding boxes
    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(frame, "FACE", (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

    if len(faces) > 0:
        print(f"[DETECT] {len(faces)} face(s) detected")

    # Re-encode to JPEG at configured quality
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
    success, encoded = cv2.imencode('.jpg', frame, encode_params)
    if not success:
        print("[WARN] Failed to re-encode JPEG")
        return None

    return encoded.tobytes()


def upload_frame_async(jpeg_bytes, frame_num):
    """
    Background upload function — runs in a separate thread.
    Base64-encodes the processed JPEG and POSTs to the relay server.
    This function NEVER blocks the main serial reading loop.
    """
    b64_string = base64.b64encode(jpeg_bytes).decode('utf-8')
    payload = {"image": b64_string}

    try:
        resp = requests.post(RELAY_URL, json=payload, timeout=5)
        size_kb = len(jpeg_bytes) / 1024
        if resp.status_code == 200:
            print(f"  [✓] Frame #{frame_num:04d} uploaded | {size_kb:.1f} KB")
        else:
            print(f"  [✗] Frame #{frame_num:04d} upload returned {resp.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"  [✗] Frame #{frame_num:04d} upload failed: {e}")


def main():
    global upload_thread, frames_skipped

    print("=" * 60)
    print("  ESP32-CAM Serial Publisher (Zero-Latency Edition)")
    print(f"  Port:      {SERIAL_PORT} @ {BAUD_RATE} baud")
    print(f"  Relay:     {RELAY_URL}")
    print(f"  Output:    {OUTPUT_WIDTH}x{OUTPUT_HEIGHT} @ Q{JPEG_QUALITY}")
    print(f"  Uploads:   ASYNC (non-blocking threads)")
    print(f"  Buffer:    PURGED every iteration")
    print("=" * 60)

    # Load face detection model
    face_cascade = load_face_cascade()

    # Open serial port with timeout
    print(f"\n[INFO] Opening serial port {SERIAL_PORT}...")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
    except serial.SerialException as e:
        print(f"[FATAL] Cannot open {SERIAL_PORT}: {e}")
        sys.exit(1)

    print("[INFO] Serial port opened. Waiting for frames...\n")

    frame_num = 0
    consecutive_errors = 0

    try:
        while True:
            # ═══════════════════════════════════════════════════
            # CRITICAL: Purge the serial buffer FIRST.
            # This discards any old backed-up data and ensures
            # we ONLY read the absolute newest live frame.
            # Without this, network latency causes a growing
            # backlog of stale frames in the serial buffer.
            # ═══════════════════════════════════════════════════
            ser.reset_input_buffer()

            # Find sync header for the next frame
            find_sync_header(ser)

            # Read JPEG payload
            jpeg_data = read_frame_payload(ser)
            if jpeg_data is None:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print("[WARN] Too many consecutive errors, resetting serial...")
                    ser.reset_input_buffer()
                    consecutive_errors = 0
                continue

            consecutive_errors = 0

            # Process frame with face detection (fast, local)
            processed = process_frame(jpeg_data, face_cascade)
            if processed is None:
                continue

            frame_num += 1

            # ═══════════════════════════════════════════════════
            # ASYNC NON-BLOCKING UPLOAD
            # Check if the previous upload thread is still running.
            # If YES → skip this frame (prevent backlog!)
            # If NO  → spawn a new background thread for upload
            # ═══════════════════════════════════════════════════
            if upload_thread is not None and upload_thread.is_alive():
                # Previous upload still in progress — DROP this frame
                frames_skipped += 1
                print(f"  [SKIP] Frame #{frame_num:04d} dropped "
                      f"(upload busy, total skipped: {frames_skipped})")
                continue

            # Previous upload finished (or first frame) — fire new upload
            upload_thread = threading.Thread(
                target=upload_frame_async,
                args=(processed, frame_num),
                daemon=True  # Daemon threads die with the main process
            )
            upload_thread.start()

    except KeyboardInterrupt:
        print(f"\n\n[INFO] Stopped by user.")
        print(f"  Total frames processed: {frame_num}")
        print(f"  Total frames skipped:   {frames_skipped}")
    finally:
        ser.close()
        print("[INFO] Serial port closed.")


if __name__ == "__main__":
    main()
