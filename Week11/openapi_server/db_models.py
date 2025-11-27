# swagger_server/db_models.py
from mongoengine import Document, StringField, FloatField, ListField, URLField, DateTimeField
import datetime

class Product(Document):
    """
    Model MongoEngine cho Product.
    Các tên trường nên khớp với schema trong OpenAPI.
    """
    name = StringField(required=True, max_length=200)
    price = FloatField(required=True)
    description = StringField()

    # Giúp chuyển đổi Document của MongoEngine sang dict
    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "price": self.price,
            "description": self.description
        }

class Webhook(Document):
    """
    Lưu trữ các URL đăng ký nhận thông báo (Subscribers)
    Ví dụ: Hệ thống Email Marketing đăng ký nhận sự kiện 'product_created'
    """
    url = URLField(required=True) # Endpoint của client nhận thông báo
    events = ListField(StringField(), required=True) # ['product.created', 'product.updated']
    secret = StringField() # Dùng để ký request (HMAC) bảo mật
    created_at = DateTimeField(default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'id': str(self.id),
            'url': self.url,
            'events': self.events,
            'created_at': self.created_at.isoformat()
        }