# extensions.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Khởi tạo Limiter nhưng chưa gắn vào app (sẽ gắn sau ở wsgi.py)
limiter = Limiter(key_func=get_remote_address)