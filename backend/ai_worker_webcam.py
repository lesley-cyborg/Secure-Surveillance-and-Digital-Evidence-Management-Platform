"""
Phase C AI Worker - Webcam Demo
This script simulates an AI-powered surveillance camera using the laptop webcam.
It sends periodic heartbeats to the backend to update camera status.
"""

import os
import sys
import time
import logging
import requests
import cv2
from datetime import datetime, timezone

# --- Configuration ---
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
CAMERA_ID = os.getenv("CAMERA_ID", "5aeb9e06-05bb-4530-ab29-524b0b411af6")  # CAM-001 UUID
AI_SERVICE_TOKEN = os.getenv("AI_INGESTION_SERVICE_TOKEN", "dev-ai-service-token-change-me")
WEBCAM_INDEX = int(os.getenv("WEBCAM_INDEX", "0"))  # 0 = default webcam

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def send_heartbeat(status: str, detail: str | None = None) -> bool:
    """Send a heartbeat PATCH request to the backend."""
    url = f"{BACKEND_URL}/api/v1/cameras/{CAMERA_ID}/heartbeat"
    headers = {
        "Authorization": f"Bearer {AI_SERVICE_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "status": status,
        "lastSeenAt": datetime.now(timezone.utc).isoformat(),
    }
    if detail:
        payload["detail"] = detail

    try:
        response = requests.patch(url, json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            logger.info(f"✓ Heartbeat sent: {status}")
            return True
        else:
            logger.error(f"✗ Heartbeat failed: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Could not reach backend: {e}")
        return False


def run_webcam_worker():
    """Main worker loop: capture frames and send heartbeats."""
    logger.info("=" * 60)
    logger.info("Starting AI Worker (Webcam Demo)")
    logger.info(f"Backend: {BACKEND_URL}")
    logger.info(f"Camera ID: {CAMERA_ID}")
    logger.info(f"Webcam Index: {WEBCAM_INDEX}")
    logger.info("=" * 60)

    # Open webcam
    logger.info(f"Opening webcam (index {WEBCAM_INDEX})...")
    cap = cv2.VideoCapture(WEBCAM_INDEX)
    
    if not cap.isOpened():
        logger.error(f"Failed to open webcam at index {WEBCAM_INDEX}")
        logger.info("Trying index 1...")
        cap = cv2.VideoCapture(WEBCAM_INDEX + 1)
        if not cap.isOpened():
            logger.error("Could not open any webcam. Exiting.")
            sys.exit(1)

    logger.info("✓ Webcam opened successfully")
    logger.info("Sending initial ONLINE heartbeat...")
    send_heartbeat("ONLINE", "Webcam stream started")

    last_heartbeat_time = time.time()
    frame_count = 0

    try:
        while True:
            # Capture frame
            ret, frame = cap.read()
            
            if not ret:
                logger.warning("✗ Failed to read frame. Marking DEGRADED.")
                send_heartbeat("DEGRADED", "Frame capture failed")
                time.sleep(2)
                continue

            frame_count += 1

            # --- AI Processing (Placeholder) ---
            # In a real system, you would run YOLO/ResNet here:
            # detections = model.predict(frame)
            # if detections:
            #     send_detection_event(detections)

            # Send periodic heartbeat
            current_time = time.time()
            if current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL:
                send_heartbeat("ONLINE")
                last_heartbeat_time = current_time

            # Show the webcam feed (comment out for headless operation)
            cv2.imshow("AI Worker - Webcam", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                 break

            # Small delay to control frame rate (adjust as needed)
            time.sleep(0.03)  # ~30 FPS

    except KeyboardInterrupt:
        logger.info("\nShutting down worker...")
    finally:
        logger.info("Sending final OFFLINE heartbeat...")
        send_heartbeat("OFFLINE", "Worker shutdown")
        cap.release()
        cv2.destroyAllWindows()
        logger.info("✓ Worker stopped cleanly")


if __name__ == "__main__":
    run_webcam_worker()