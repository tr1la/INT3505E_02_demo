from flask import Flask, request, jsonify, make_response, send_from_directory, g
from flask_cors import CORS
import hashlib
import json
import jwt
import datetime
from functools import wraps
from flask_swagger_ui import get_swaggerui_blueprint
from dotenv import load_dotenv
from bson import ObjectId
from pymongo import MongoClient
from mongoengine import Document, StringField, BooleanField, connect, DoesNotExist
import os
import re

# ------------------ Setup ------------------
load_dotenv()
app = Flask(__name__, static_folder=None)
CORS(app)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "defaultsecret")
app.config['MONGO_URI'] = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
app.config['MONGO_DB_NAME'] = os.getenv("MONGO_DB_NAME", "soa_demo")
app.config['API_VERSION_STRATEGY'] =  "header" # uri, query, header

# ------------------ MongoDB setup ------------------
# PyMongo for v1
client = MongoClient(app.config['MONGO_URI'])
db = client[app.config['MONGO_DB_NAME']]
books_col = db['book']

# MongoEngine for v2
connect(db=app.config['MONGO_DB_NAME'], host=app.config['MONGO_URI'])

# ------------------ MongoEngine Model ------------------
class Book(Document):
    title = StringField(required=True)
    author = StringField(required=True)
    available = BooleanField(default=True)
    year_published = StringField()
    def to_dict(self):
        return {
            "_id": str(self.id),
            "title": self.title,
            "author": self.author,
            "available": self.available,
            "year_published": self.year_published
        }
        
# ------------------ Helper functions ------------------
def generate_etag(data_dict):
    data_str = json.dumps(data_dict, sort_keys=True, default=str)
    return hashlib.md5(data_str.encode('utf-8')).hexdigest()

def success_response(data=None, message=None, status_code=200, etag=None):
    response = make_response(jsonify({
        "status": "success",
        "data": data,
        "message": message
    }), status_code)
    if etag:
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, max-age=120"
    return response

def error_response(message, status_code=400):
    return make_response(jsonify({
        "status": "error",
        "data": None,
        "message": message
    }), status_code)

def serialize_doc(doc):
    doc['_id'] = str(doc['_id'])
    return doc

# ------------------ API Version Detection ------------------
def get_api_version():
    """Detect API version based on configured strategy"""
    strategy = app.config['API_VERSION_STRATEGY']
    
    # Strategy 1: URI Path versioning
    if strategy == 'uri':
        # Already handled by route definitions
        return g.get('api_version', '1')
    
    # Strategy 2: Query parameter versioning
    elif strategy == 'query':
        version = request.args.get('version', '1')
        return version
    
    # Strategy 3: Custom header versioning
    elif strategy == 'header':
        version = request.headers.get('api-version', '1')
        return version
    
    # Strategy 4: Content negotiation
    elif strategy == 'content':
        accept = request.headers.get('Accept', '')
        # Parse: application/vnd.library.v1+json or application/vnd.library+json; version=1
        match = re.search(r'version=(\d+)', accept)
        if match:
            return match.group(1)
        match = re.search(r'\.v(\d+)\+', accept)
        if match:
            return match.group(1)
        return '1'
    
    return '1'

def version_required(version):
    """Decorator to enforce specific API version"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            current_version = get_api_version()
            if current_version != str(version):
                return error_response(f"API version {version} required", 400)
            return f(*args, **kwargs)
        return decorated
    return decorator

# ------------------ AUTH ------------------
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        if not token:
            return error_response("Token is missing", 401)
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['user']
        except jwt.ExpiredSignatureError:
            return error_response("Token expired", 401)
        except jwt.InvalidTokenError:
            return error_response("Invalid token", 401)
        return f(current_user, *args, **kwargs)
    return decorated

# ------------------ LOGIN ENDPOINTS ------------------
# Strategy 1: URI Path versioning
@app.route('/api/v1/login', methods=['POST'])
def login_v1():
    g.api_version = '1'
    return login_handler()

@app.route('/api/v2/login', methods=['POST'])
def login_v2():
    g.api_version = '2'
    return login_handler()

# Strategy 2, 3, 4: Single endpoint with version detection
@app.route('/api/login', methods=['POST'])
def login_unified():
    return login_handler()

def login_handler():
    body = request.get_json()
    username = body.get('username')
    password = body.get('password')
    if username == 'admin' and password == '123456':
        token = jwt.encode({
            'user': username,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        return success_response({"token": token}, "Login successful")
    return error_response("Invalid credentials", 401)

# ------------------ BOOKS ENDPOINTS - V1 (PyMongo) ------------------
# Strategy 1: URI Path versioning
@app.route('/api/v1/books', methods=['GET'])
@token_required
def get_books_v1(current_user):
    g.api_version = '1'
    return get_books_v1_handler(current_user)

@app.route('/api/v1/books', methods=['POST'])
@token_required
def create_book_v1(current_user):
    g.api_version = '1'
    return create_book_v1_handler(current_user)

@app.route('/api/v1/books/<book_id>', methods=['GET'])
@token_required
def get_book_v1(current_user, book_id):
    g.api_version = '1'
    return get_book_v1_handler(current_user, book_id)

@app.route('/api/v1/books/<book_id>', methods=['PUT'])
@token_required
def update_book_v1(current_user, book_id):
    g.api_version = '1'
    return update_book_v1_handler(current_user, book_id)

@app.route('/api/v1/books/<book_id>', methods=['DELETE'])
@token_required
def delete_book_v1(current_user, book_id):
    g.api_version = '1'
    return delete_book_v1_handler(current_user, book_id)

# V1 Handlers (PyMongo)
def get_books_v1_handler(current_user):
    query = {}
    available = request.args.get('available')
    if available is not None:
        query['available'] = available.lower() == 'true'

    title = request.args.get('title')
    author = request.args.get('author')
    if title:
        query['title'] = {'$regex': title, '$options': 'i'}
    if author:
        query['author'] = {'$regex': author, '$options': 'i'}

    books = list(books_col.find(query).limit(20))
    books = [serialize_doc(b) for b in books]
    etag = generate_etag(books)
    return success_response({"books": books}, "Books fetched successfully (v1)", etag=etag)

def create_book_v1_handler(current_user):
    data = request.get_json()
    if not data or not data.get('title') or not data.get('author'):
        return error_response("Missing title or author", 400)
    book = {
        "title": data['title'],
        "author": data['author'],
        "available": True
    }
    result = books_col.insert_one(book)
    book['_id'] = str(result.inserted_id)
    etag = generate_etag(book)
    return success_response(book, "Book created (v1)", 201, etag)

def get_book_v1_handler(current_user, book_id):
    book = books_col.find_one({"_id": ObjectId(book_id)})
    if not book:
        return error_response("Book not found", 404)
    book = serialize_doc(book)
    etag = generate_etag(book)
    client_etag = request.headers.get('If-None-Match')
    if client_etag == etag:
        return '', 304
    return success_response(book, etag=etag)

def update_book_v1_handler(current_user, book_id):
    data = request.get_json()
    update_fields = {}
    for key in ['title', 'author', 'available']:
        if key in data:
            update_fields[key] = data[key]
    result = books_col.update_one({"_id": ObjectId(book_id)}, {"$set": update_fields})
    if result.matched_count == 0:
        return error_response("Book not found", 404)
    book = books_col.find_one({"_id": ObjectId(book_id)})
    book = serialize_doc(book)
    return success_response(book, "Book updated (v1)", etag=generate_etag(book))

def delete_book_v1_handler(current_user, book_id):
    result = books_col.delete_one({"_id": ObjectId(book_id)})
    if result.deleted_count == 0:
        return error_response("Book not found", 404)
    return success_response(None, "Book deleted (v1)")

# ------------------ BOOKS ENDPOINTS - V2 (MongoEngine) ------------------
# Strategy 1: URI Path versioning
@app.route('/api/v2/books', methods=['GET'])
@token_required
def get_books_v2(current_user):
    g.api_version = '2'
    return get_books_v2_handler(current_user)

@app.route('/api/v2/books', methods=['POST'])
@token_required
def create_book_v2(current_user):
    g.api_version = '2'
    return create_book_v2_handler(current_user)

@app.route('/api/v2/books/<book_id>', methods=['GET'])
@token_required
def get_book_v2(current_user, book_id):
    g.api_version = '2'
    return get_book_v2_handler(current_user, book_id)

@app.route('/api/v2/books/<book_id>', methods=['PUT'])
@token_required
def update_book_v2(current_user, book_id):
    g.api_version = '2'
    return update_book_v2_handler(current_user, book_id)

@app.route('/api/v2/books/<book_id>', methods=['DELETE'])
@token_required
def delete_book_v2(current_user, book_id):
    g.api_version = '2'
    return delete_book_v2_handler(current_user, book_id)

# V2 Handlers (MongoEngine)
def get_books_v2_handler(current_user):
    query = {}
    available = request.args.get('available')
    if available is not None:
        query['available'] = available.lower() == 'true'

    title = request.args.get('title')
    author = request.args.get('author')
    if title:
        query['title__icontains'] = title
    if author:
        query['author__icontains'] = author

    books = Book.objects(**query)[:20]
    books_list = [b.to_dict() for b in books]
    etag = generate_etag(books_list)
    return success_response({"books": books_list}, "Books fetched successfully (v2)", etag=etag)

def create_book_v2_handler(current_user):
    data = request.get_json()
    if not data or not data.get('title') or not data.get('author'):
        return error_response("Missing title or author", 400)
    book = Book(title=data['title'], author=data['author'], available=True)
    book.save()
    book_dict = book.to_dict()
    return success_response(book_dict, "Book created (v2)", 201, generate_etag(book_dict))

def get_book_v2_handler(current_user, book_id):
    try:
        book = Book.objects.get(id=book_id)
    except DoesNotExist:
        return error_response("Book not found", 404)
    book_dict = book.to_dict()
    etag = generate_etag(book_dict)
    client_etag = request.headers.get('If-None-Match')
    if client_etag == etag:
        return '', 304
    return success_response(book_dict, etag=etag)

def update_book_v2_handler(current_user, book_id):
    data = request.get_json()
    try:
        book = Book.objects.get(id=book_id)
    except DoesNotExist:
        return error_response("Book not found", 404)
    for key in ['title', 'author', 'available']:
        if key in data:
            setattr(book, key, data[key])
    book.save()
    book_dict = book.to_dict()
    return success_response(book_dict, "Book updated (v2)", etag=generate_etag(book_dict))

def delete_book_v2_handler(current_user, book_id):
    try:
        book = Book.objects.get(id=book_id)
    except DoesNotExist:
        return error_response("Book not found", 404)
    book.delete()
    return success_response(None, "Book deleted (v2)")

# ------------------ UNIFIED ENDPOINTS (for query/header/content strategies) ------------------
@app.route('/api/books', methods=['GET'])
@token_required
def get_books_unified(current_user):
    version = get_api_version()
    if version == '2':
        return get_books_v2_handler(current_user)
    return get_books_v1_handler(current_user)

@app.route('/api/books', methods=['POST'])
@token_required
def create_book_unified(current_user):
    version = get_api_version()
    if version == '2':
        return create_book_v2_handler(current_user)
    return create_book_v1_handler(current_user)

@app.route('/api/books/<book_id>', methods=['GET'])
@token_required
def get_book_unified(current_user, book_id):
    version = get_api_version()
    if version == '2':
        return get_book_v2_handler(current_user, book_id)
    return get_book_v1_handler(current_user, book_id)

@app.route('/api/books/<book_id>', methods=['PUT'])
@token_required
def update_book_unified(current_user, book_id):
    version = get_api_version()
    if version == '2':
        return update_book_v2_handler(current_user, book_id)
    return update_book_v1_handler(current_user, book_id)

@app.route('/api/books/<book_id>', methods=['DELETE'])
@token_required
def delete_book_unified(current_user, book_id):
    version = get_api_version()
    if version == '2':
        return delete_book_v2_handler(current_user, book_id)
    return delete_book_v1_handler(current_user, book_id)

# ------------------ API Info Endpoint ------------------
@app.route('/api/info', methods=['GET'])
def api_info():
    return success_response({
        "strategy": app.config['API_VERSION_STRATEGY'],
        "available_versions": ['1', '2'],
        "usage_examples": {
            "uri": "GET /api/v1/books or /api/v2/books",
            "query": "GET /api/books?version=1 or version=2",
            "header": "GET /api/books with header 'api-version: 1'",
            "content": "GET /api/books with header 'Accept: application/vnd.library.v1+json'"
        }
    }, "API information")

# ------------------ Swagger ------------------
SWAGGER_URL = '/docs'
API_URL = '/static/swagger-v3.yaml'
swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL, config={'app_name': "Book Management API"})
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

@app.route('/static/<path:filename>')
def static_files(filename):
    static_dir = os.path.join(app.root_path, '..', 'static')
    return send_from_directory(static_dir, filename)

@app.route('/')
def home():
    # Kiểm tra MongoDB connection
    try:
        db_name = app.config['MONGO_DB_NAME']
        collection_names = db.list_collection_names()
        has_book_collection = 'book' in collection_names
        book_count = books_col.count_documents({})
    except Exception as e:
        db_name = "Connection failed"
        collection_names = []
        has_book_collection = False
        book_count = 0
        print("MongoDB connection error:", e)
    return jsonify({
        "message": "Book Management API",
        "versioning_strategy": app.config['API_VERSION_STRATEGY'],
        "docs": "/docs",
        "info": "/api/info",
        "mongo_db_name": db_name,
        "collections": collection_names,
        "has_book_collection": has_book_collection,
        "book_count": book_count
    })

if __name__ == '__main__':
    app.run(debug=True, port=5001)