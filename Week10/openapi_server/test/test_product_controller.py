import unittest

from flask import json

from openapi_server.models.error import Error  # noqa: E501
from openapi_server.models.product import Product  # noqa: E501
from openapi_server.models.product_input import ProductInput  # noqa: E501
from openapi_server.test import BaseTestCase


class TestProductController(BaseTestCase):
    """ProductController integration test stubs"""

    def test_create_product(self):
        """Test case for create_product

        Tạo một sản phẩm mới
        """
        product_input = {"price":1299.99,"name":"Laptop","description":"Một chiếc laptop mạnh mẽ"}
        headers = { 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        response = self.client.open(
            '/api/v1/products',
            method='POST',
            headers=headers,
            data=json.dumps(product_input),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_delete_product(self):
        """Test case for delete_product

        Xóa một sản phẩm
        """
        headers = { 
        }
        response = self.client.open(
            '/api/v1/products/{product_id}'.format(product_id='605c7211f0a2d1001f2f3a6a'),
            method='DELETE',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_all_products(self):
        """Test case for get_all_products

        Lấy danh sách tất cả sản phẩm
        """
        headers = { 
            'Accept': 'application/json',
        }
        response = self.client.open(
            '/api/v1/products',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_product_by_id(self):
        """Test case for get_product_by_id

        Lấy thông tin sản phẩm bằng ID
        """
        headers = { 
            'Accept': 'application/json',
        }
        response = self.client.open(
            '/api/v1/products/{product_id}'.format(product_id='605c7211f0a2d1001f2f3a6a'),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_update_product(self):
        """Test case for update_product

        Cập nhật một sản phẩm đã có
        """
        product_input = {"price":1299.99,"name":"Laptop","description":"Một chiếc laptop mạnh mẽ"}
        headers = { 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        response = self.client.open(
            '/api/v1/products/{product_id}'.format(product_id='605c7211f0a2d1001f2f3a6a'),
            method='PUT',
            headers=headers,
            data=json.dumps(product_input),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
