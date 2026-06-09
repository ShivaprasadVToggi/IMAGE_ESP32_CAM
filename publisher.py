"""
ESP32-CAM Serial Publisher
==========================
Reads raw JPEG frames from an ESP32-CAM over USB serial,
performs local face detection using OpenCV Haar Cascades,
draws green bounding boxes, and uploads the processed frame
to the cloud relay server via HTTP POST.

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

import cv2
import numpy as np
import requests

# ═══════════════════════════════════════════════════════════════
# ▸ CONFIGURATION — Update these before running
# ═══════════════════════════════════════════════════════════════
RELAY_URL = "https://YOUR-RELAY-SERVER.onrender.com/upload"
# For local testing: "http://localhost:3001/upload"

SERIAL_PORT = "COM9"
BAUD_RATE = 115200

# Output resolution for face detection and upload
OUTPUT_WIDTH = 480
OUTPUT_HEIGHT = 360

# JPEG encoding quality (0-100, lower = smaller file)
JPEG_QUALITY = 70

# Face detection parameters
FACE_SCALE_FACTOR = 1.1
FACE_MIN_NEIGHBORS = 5
FACE_MIN_SIZE = (30, 30)

# Sync header bytes
SYNC_BYTE_1 = 0xAA
SYNC_BYTE_2 = 0xBB
# ═══════════════════════════════════════════════════════════════


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
    Returns True when found, blocks until then.
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

    # Sanity check: JPEG frames should be between 1KB and 500KB
    if frame_size < 1024 or frame_size > 512000:
        print(f"[WARN] Suspicious frame size: {frame_size} bytes, skipping")
        return None

    # Read the JPEG payload
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
    re-encode to JPEG.
    Returns processed JPEG bytes.
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

    # Face detection
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
        # Optional: label
        cv2.putText(frame, "FACE", (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

    if len(faces) > 0:
        print(f"[DETECT] {len(faces)} face(s) detected")

    # Re-encode to JPEG
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
    success, encoded = cv2.imencode('.jpg', frame, encode_params)
    if not success:
        print("[WARN] Failed to re-encode JPEG")
        return None

    return encoded.tobytes()


def upload_frame(jpeg_bytes):
    """
    Base64-encode the processed JPEG and POST to the relay server.
    """
    b64_string = base64.b64encode(jpeg_bytes).decode('utf-8')
    payload = {"image": b64_string}

    try:
        resp = requests.post(RELAY_URL, json=payload, timeout=3)
        if resp.status_code == 200:
            return True
        else:
            print(f"[WARN] Upload returned status {resp.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Upload failed: {e}")
        return False


def main():
    print("=" * 56)
    print("  ESP32-CAM Serial Publisher")
    print(f"  Port: {SERIAL_PORT} @ {BAUD_RATE} baud")
    print(f"  Relay: {RELAY_URL}")
    print(f"  Output: {OUTPUT_WIDTH}x{OUTPUT_HEIGHT} @ Q{JPEG_QUALITY}")
    print("=" * 56)

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
    MAX_CONSECUTIVE_ERRORS = 20

    try:
        while True:
            # Find sync header
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

            # Process with face detection
            processed = process_frame(jpeg_data, face_cascade)
            if processed is None:
                continue

            # Upload to relay
            frame_num += 1
            size_kb = len(processed) / 1024
            success = upload_frame(processed)

            status = "✓" if success else "✗"
            print(f"  [{status}] Frame #{frame_num:04d} | "
                  f"{size_kb:.1f} KB | "
                  f"Raw: {len(jpeg_data)} B → Processed: {len(processed)} B")

    except KeyboardInterrupt:
        print(f"\n\n[INFO] Stopped. Total frames sent: {frame_num}")
    finally:
        ser.close()
        print("[INFO] Serial port closed.")


if __name__ == "__main__":
    main()
