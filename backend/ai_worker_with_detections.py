"""
Phase C AI Worker - Webcam + YOLO Detection
Captures video, runs object detection, sends heartbeats + detection events to backend.
"""

import os
import sys
import time
import logging
import requests
import cv2
from datetime import datetime, timezone
from ultralytics import YOLO

# --- Configuration ---
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
CAMERA_ID = os.getenv("CAMERA_ID", "5aeb9e06-05bb-4530-ab29-524b0b411af6")
AI_SERVICE_TOKEN = os.getenv("AI_INGESTION_SERVICE_TOKEN", "dev-ai-service-token-change-me")
WEBCAM_INDEX = int(os.getenv("WEBCAM_INDEX", "0"))

HEARTBEAT_INTERVAL = 30
DETECTION_CONFIDENCE_THRESHOLD = 0.5  # Only send detections above this confidence

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def send_heartbeat(status: str, detail: str | None = None) -> bool:
    """Send heartbeat to backend."""
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
            logger.info(f"✓ Heartbeat: {status}")
            return True
        else:
            logger.error(f"✗ Heartbeat failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Backend unreachable: {e}")
        return False


def send_detection_event(label: str, confidence: float, bounding_box: dict) -> bool:
    """Send a detection event to the backend incident sink."""
    url = f"{BACKEND_URL}/internal/v1/ai/detection-events"
    headers = {
        "Authorization": f"Bearer {AI_SERVICE_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "cameraId": CAMERA_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "confidence": confidence,
        "boundingBox": bounding_box,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code in [200, 201]:
            logger.info(f"✓ Detection sent: {label} ({confidence:.2f})")
            return True
        else:
            logger.error(f"✗ Detection failed: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Could not send detection: {e}")
        return False


def run_ai_worker():
    """Main worker loop: capture → detect → report."""
    logger.info("=" * 60)
    logger.info("Starting AI Worker (Webcam + YOLO Detection)")
    logger.info(f"Camera ID: {CAMERA_ID}")
    logger.info("=" * 60)

    # Load YOLO model (downloads automatically on first run)
    logger.info("Loading YOLO model...")
    model = YOLO("yolov8n.pt")  # nano model for speed; use yolov8s.pt for better accuracy
    logger.info("✓ YOLO model loaded")

    # Open webcam
    logger.info(f"Opening webcam (index {WEBCAM_INDEX})...")
    cap = cv2.VideoCapture(WEBCAM_INDEX)
    
    if not cap.isOpened():
        logger.error("Failed to open webcam. Exiting.")
        sys.exit(1)

    logger.info("✓ Webcam opened")
    send_heartbeat("ONLINE", "AI worker started with YOLO detection")

    last_heartbeat_time = time.time()
    detection_count = 0

    try:
        while True:
            ret, frame = cap.read()
            
            if not ret:
                logger.warning("✗ Frame read failed")
                send_heartbeat("DEGRADED", "Frame capture failed")
                time.sleep(2)
                continue

            # --- YOLO Detection ---
            results = model(frame, verbose=False)
            
            # Process detections
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        confidence = float(box.conf[0])
                        if confidence < DETECTION_CONFIDENCE_THRESHOLD:
                            continue
                        
                        class_id = int(box.cls[0])
                        label = model.names[class_id]
                        
                        # Extract bounding box (xyxy format: x1, y1, x2, y2)
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        
                        # Convert to {x, y, width, height} format
                        bounding_box = {
                            "x": int(x1),
                            "y": int(y1),
                            "width": int(x2 - x1),
                            "height": int(y2 - y1)
                        }
                        
                        # Send detection to backend
                        send_detection_event(label, confidence, bounding_box)
                        detection_count += 1

                        # Optional: Draw box on frame (for visualization)
                        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                        cv2.putText(frame, f"{label} {confidence:.2f}", (int(x1), int(y1) - 10),
                                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Periodic heartbeat
            current_time = time.time()
            if current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL:
                send_heartbeat("ONLINE", f"Processed {detection_count} detections")
                last_heartbeat_time = current_time

            # Show annotated feed
            cv2.imshow("AI Worker - Detection", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                 break

            time.sleep(0.03)  # ~30 FPS

    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    finally:
        send_heartbeat("OFFLINE", "Worker shutdown")
        cap.release()
        cv2.destroyAllWindows()
        logger.info(f"✓ Worker stopped. Total detections: {detection_count}")


if __name__ == "__main__":
    run_ai_worker()