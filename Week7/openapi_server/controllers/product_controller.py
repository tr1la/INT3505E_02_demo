import connexion
from typing import Dict
from typing import Tuple
from typing import Union

from openapi_server.models.error import Error  # noqa: E501
from openapi_server.models.product import Product as ApiProduct  # noqa: E501
from openapi_server.models.product_input import ProductInput  # noqa: E501
from openapi_server import util
from openapi_server.db_models import Product as DbProduct
from mongoengine.errors import DoesNotExist, ValidationError
from flask import request, jsonify

def create_product():
    """Tạo sản phẩm mới"""
    if connexion.request.is_json:
        # connexion tự động xác thực body dựa trên file OpenAPI
        body = ApiProduct.from_dict(connexion.request.get_json())
        
        try:
            # Tạo instance model DB
            new_product = DbProduct(
                name=body.name,
                price=body.price,
                description=body.description
            )
            new_product.save() # Lưu vào MongoDB
            
            # Trả về 201 Created
            return new_product.to_dict(), 201
        except ValidationError as e:
            return {'message': str(e)}, 400
        except Exception as e:
            return {'message': str(e)}, 500
    
    return 'Invalid input', 400

def get_all_products():  # <-- Hàm bạn đang thiếu
    """Lấy danh sách tất cả sản phẩm"""
    try:
        # Lấy tất cả document từ collection
        all_products = DbProduct.objects.all()
        
        # Chuyển đổi danh sách Document của MongoEngine sang list of dicts
        # Chúng ta dùng hàm to_dict() đã định nghĩa trong db_models.py
        results = [product.to_dict() for product in all_products]
        
        return results, 200  # Trả về danh sách và status code 200
        
    except Exception as e:
        return {'message': str(e)}, 500

def get_product_by_id(product_id):
    """Lấy thông tin sản phẩm bằng ID"""
    try:
        # Tìm sản phẩm bằng ID trong Mongo
        product = DbProduct.objects.get(id=product_id)
        return product.to_dict(), 200
    except DoesNotExist:
        return {'message': 'Không tìm thấy sản phẩm'}, 404
    except Exception as e:
        return {'message': str(e)}, 500


def update_product(product_id):
    """Cập nhật sản phẩm"""
    if connexion.request.is_json:
        body = ApiProduct.from_dict(connexion.request.get_json())
        
        try:
            product = DbProduct.objects.get(id=product_id)
            
            # Cập nhật các trường
            product.name = body.name
            product.price = body.price
            product.description = body.description
            
            product.save() # Lưu lại thay đổi
            return product.to_dict(), 200
        except DoesNotExist:
            return {'message': 'Không tìm thấy sản phẩm'}, 404
        except ValidationError as e:
            return {'message': str(e)}, 400
        except Exception as e:
            return {'message': str(e)}, 500

    return 'Invalid input', 400


def delete_product(product_id):
    """Xóa một sản phẩm"""
    try:
        product = DbProduct.objects.get(id=product_id)
        product.delete() # Xóa khỏi DB
        
        # Trả về 204 No Content
        return '', 204 
    except DoesNotExist:
        return {'message': 'Không tìm thấy sản phẩm'}, 404
    except Exception as e:
        return {'message': str(e)}, 500