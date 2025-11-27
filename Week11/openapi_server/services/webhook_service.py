import requests
import threading
import logging
import datetime
from openapi_server.db_models import Webhook

logger = logging.getLogger(__name__)

def _send_request(url, payload):
    """Hàm gửi request thực tế (chạy ngầm)"""
    try:
        # Giả lập gửi POST request tới client
        response = requests.post(url, json=payload, timeout=5)
        logger.info(f"Webhook sent to {url} | Status: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to send webhook to {url}: {e}")

def trigger_event(event_type, data):
    """
    Hàm này được gọi từ Controller.
    Nó tìm các subscriber quan tâm đến event_type và gửi thông báo.
    """
    # 1. Tìm tất cả webhook đăng ký sự kiện này
    subscribers = Webhook.objects(events=event_type)
    
    if not subscribers:
        return

    payload = {
        'event': event_type,
        'data': data,
        'timestamp': str(datetime.datetime.now(datetime.timezone.utc))
    }

    # 2. Gửi bất đồng bộ (Fire and Forget)
    for sub in subscribers:
        logger.info(f"Triggering webhook {event_type} for {sub.url}")
        # Tạo luồng riêng để không block API chính
        thread = threading.Thread(target=_send_request, args=(sub.url, payload))
        thread.start()