# ai-engine/integrations/backend/heartbeat_client.py
import httpx
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class HeartbeatClient:
    def __init__(self, camera_id: str, backend_url: str, service_token: str):
        self.camera_id = camera_id
        self.url = f"{backend_url}/api/v1/cameras/{camera_id}/heartbeat"
        self.headers = {
            "Authorization": f"Bearer {service_token}",
            "Content-Type": "application/json"
        }
        # Reuse connection pool if you want, but simple client is fine for FYP
        self.client = httpx.Client(timeout=5.0)

    def send(self, status: str, detail: str | None = None):
        """Sends PATCH request to update camera status."""
        payload = {
            "status": status,
            "lastSeenAt": datetime.now(timezone.utc).isoformat()
        }
        if detail:
            payload["detail"] = detail
            
        try:
            resp = self.client.patch(self.url, json=payload, headers=self.headers)
            if resp.status_code == 200:
                logger.info(f"[Heartbeat] Camera {self.camera_id} -> {status}")
            else:
                logger.error(f"[Heartbeat] Failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"[Heartbeat] Network Error: {e}")
            
    def close(self):
        self.client.close()