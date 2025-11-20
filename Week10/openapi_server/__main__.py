#!/usr/bin/env python3

import connexion
import logging
import os
from mongoengine import connect
from openapi_server import encoder
from prometheus_flask_exporter import PrometheusMetrics
from openapi_server.controllers.extensions import limiter

# --- PHẦN CẤU HÌNH GLOBAL (Chạy ngay khi Gunicorn import file này) ---

# 1. Cấu hình Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 2. Kết nối Database
# (Gunicorn cần kết nối DB ngay khi khởi động worker)
mongo_uri = os.getenv(
    'MONGO_URI', 
    'mongodb+srv://tr1la:chuviblachuoi@mymongo.teuyzcm.mongodb.net/?appName=MyMongo'
)
try:
    connect('product_db', host=mongo_uri)
    logger.info("Kết nối MongoDB thành công!")
except Exception as e:
    logger.error(f"Lỗi kết nối MongoDB: {e}")

# 3. Khởi tạo App Connexion
app = connexion.App(__name__, specification_dir='./openapi/')
app.app.json_encoder = encoder.JSONEncoder
app.add_api('openapi.yaml',
            arguments={'title': 'Product API'},
            pythonic_params=True)

# 4. Kích hoạt Monitoring & Rate Limit
# (Phải gắn vào flask_app TẠI ĐÂY thì Gunicorn mới nhận được)
flask_app = app.app

metrics = PrometheusMetrics(flask_app)
metrics.info('app_info', 'Product API Info', version='1.0.0')

limiter.init_app(flask_app)


def main():
    # Hàm này chỉ chạy khi bạn gõ lệnh: python -m openapi_server
    # Dùng để debug dưới local
    logger.info("Đang chạy chế độ Local Development...")
    app.run(port=8080)

if __name__ == '__main__':
    main()