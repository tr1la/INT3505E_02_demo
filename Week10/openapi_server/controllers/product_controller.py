# product_controller.py
import connexion
import logging
from openapi_server.models.product import Product as ApiProduct
from openapi_server.db_models import Product as DbProduct
from mongoengine.errors import DoesNotExist, ValidationError

# Import limiter từ extensions để dùng decorator
from openapi_server.controllers.extensions import limiter

# Khởi tạo logger cho file này
logger = logging.getLogger(__name__)

# --- APPLICATON ---

@limiter.limit("5 per minute")  # Rate limit: Chỉ cho phép tạo 5 sản phẩm/phút từ 1 IP
def create_product():
    """Tạo sản phẩm mới"""
    logger.info("Đang nhận request tạo sản phẩm mới") # Log INFO
    
    if connexion.request.is_json:
        body = ApiProduct.from_dict(connexion.request.get_json())
        try:
            new_product = DbProduct(
                name=body.name,
                price=body.price,
                description=body.description
            )
            new_product.save()
            
            logger.info(f"Đã tạo sản phẩm thành công: ID={new_product.id}") # Log thành công
            return new_product.to_dict(), 201
            
        except ValidationError as e:
            logger.warning(f"Lỗi Validate dữ liệu: {str(e)}") # Log Warning
            return {'message': str(e)}, 400
        except Exception as e:
            logger.error(f"Lỗi Server khi tạo sản phẩm: {str(e)}", exc_info=True) # Log Error kèm Stack Trace
            return {'message': str(e)}, 500
    
    logger.warning("Request body không phải JSON")
    return 'Invalid input', 400

@limiter.limit("2 per minute") # Cho phép xem danh sách 20 lần/phút
def get_all_products():
    """Lấy danh sách tất cả sản phẩm"""
    try:
        all_products = DbProduct.objects.all()
        results = [product.to_dict() for product in all_products]
        
        logger.info(f"Đã lấy danh sách {len(results)} sản phẩm")
        return results, 200
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sản phẩm: {str(e)}", exc_info=True)
        return {'message': str(e)}, 500

@limiter.limit("30 per minute") # Cho phép xem chi tiết nhiều hơn
def get_product_by_id(product_id):
    """Lấy thông tin sản phẩm bằng ID"""
    try:
        product = DbProduct.objects.get(id=product_id)
        return product.to_dict(), 200
    except DoesNotExist:
        logger.info(f"Không tìm thấy sản phẩm ID: {product_id}")
        return {'message': 'Không tìm thấy sản phẩm'}, 404
    except Exception as e:
        logger.error(f"Lỗi lấy sản phẩm {product_id}: {str(e)}")
        return {'message': str(e)}, 500

@limiter.limit("5 per minute")
def update_product(product_id):
    """Cập nhật sản phẩm"""
    if connexion.request.is_json:
        body = ApiProduct.from_dict(connexion.request.get_json())
        try:
            product = DbProduct.objects.get(id=product_id)
            product.name = body.name
            product.price = body.price
            product.description = body.description
            product.save()
            
            logger.info(f"Đã cập nhật sản phẩm {product_id}")
            return product.to_dict(), 200
        except DoesNotExist:
            return {'message': 'Không tìm thấy sản phẩm'}, 404
        except ValidationError as e:
            return {'message': str(e)}, 400
        except Exception as e:
            logger.error(f"Lỗi cập nhật {product_id}: {str(e)}")
            return {'message': str(e)}, 500

    return 'Invalid input', 400

@limiter.limit("5 per minute")
def delete_product(product_id):
    """Xóa một sản phẩm"""
    try:
        product = DbProduct.objects.get(id=product_id)
        product.delete()
        
        logger.info(f"Đã xóa sản phẩm {product_id}")
        return '', 204 
    except DoesNotExist:
        return {'message': 'Không tìm thấy sản phẩm'}, 404
    except Exception as e:
        logger.error(f"Lỗi xóa {product_id}: {str(e)}")
        return {'message': str(e)}, 500