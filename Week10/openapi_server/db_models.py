# swagger_server/db_models.py
from mongoengine import Document, StringField, FloatField

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