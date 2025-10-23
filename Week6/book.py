from flask import Flask, request, jsonify, make_response, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import hashlib
import json
import jwt
import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_swagger_ui import get_swaggerui_blueprint
import os
from authlib.integrations.flask_oauth2 import (
    AuthorizationServer,
    ResourceProtector,
)
from authlib.integrations.sqla_oauth2 import (
    create_query_client_func,
    create_save_token_func,
    create_revocation_endpoint,
)
from authlib.oauth2.rfc6749.grants import (
    ResourceOwnerPasswordCredentialsGrant,
)
from authlib.oauth2.rfc6750 import BearerTokenValidator

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root@localhost/soa_demo'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key_here'  # Dùng để mã hóa JWT

db = SQLAlchemy(app)

# ------------------ Model ------------------
book_categories = db.Table('book_categories',
    db.Column('book_id', db.Integer, db.ForeignKey('book.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('category.id'), primary_key=True)
)
# Bảng trung gian cho quan hệ nhiều-nều giữa User và Role
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    # Lưu các scope dưới dạng một chuỗi, phân tách bằng dấu cách
    scopes = db.Column(db.String(255), nullable=False)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    roles = db.relationship('Role', secondary=user_roles, lazy='subquery',
                            backref=db.backref('users', lazy=True))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_user_id(self):
        return self.id

    def get_allowed_scopes(self):
        user_scopes = set()
        for role in self.roles:
            user_scopes.update(role.scopes.split())
        return ' '.join(user_scopes)
    
class OAuth2Client(db.Model):
    __tablename__ = 'oauth2_client'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(48), index=True)
    client_secret = db.Column(db.String(120), nullable=False)
    client_name = db.Column(db.String(120))
    client_uri = db.Column(db.String(2000))
    grant_types = db.Column(db.String(500))
    redirect_uris = db.Column(db.String(2000))
    response_types = db.Column(db.String(500))
    scope = db.Column(db.String(500))
    token_endpoint_auth_method = db.Column(db.String(120))
    
    def get_client_id(self):
        return self.client_id
    
    def check_client_secret(self, client_secret):
        return self.client_secret == client_secret

    def check_grant_type(self, grant_type):
        return grant_type in self.grant_types.split()

    def check_response_type(self, response_type):
        return response_type in self.response_types.split()

    def check_endpoint_auth_method(self, method, endpoint):
        return method in self.token_endpoint_auth_method.split()

    def check_scope(self, scope):
        allowed = set(self.scope.split())
        requested = set(scope.split())
        return requested.issubset(allowed)
        
class OAuth2Token(db.Model):
    __tablename__ = 'oauth2_token'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    user = db.relationship('User')
    client_id = db.Column(db.String(48))
    token_type = db.Column(db.String(40))
    access_token = db.Column(db.String(255), unique=True, nullable=False)
    refresh_token = db.Column(db.String(255), index=True)
    scope = db.Column(db.String(500))
    issued_at = db.Column(db.Integer, nullable=False, default=lambda: int(time.time()))
    expires_in = db.Column(db.Integer, nullable=False, default=0)

    def is_expired(self):
        return self.issued_at + self.expires_in < time.time()

    def get_scope(self):
        return self.scope

    def get_client_id(self):
        return self.client_id
    
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def to_dict(self):
        return {"id": self.id, "name": self.name}
    

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    available = db.Column(db.Boolean, default=True)
    categories = db.relationship('Category', secondary=book_categories, lazy='subquery',
        backref=db.backref('books', lazy=True))
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "available": self.available
        }


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    join_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "join_date": self.join_date.strftime("%Y-%m-%d %H:%M:%S")
        }

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    borrow_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    return_date = db.Column(db.DateTime, nullable=True)

    member = db.relationship("Member", backref="loans")
    book = db.relationship("Book", backref="loans")

    def to_dict(self):
        return {
            "id": self.id,
            "member_id": self.member_id,
            "book_id": self.book_id,
            "borrow_date": self.borrow_date.strftime("%Y-%m-%d %H:%M:%S"),
            "return_date": self.return_date.strftime("%Y-%m-%d %H:%M:%S") if self.return_date else None
        }

# ------------------ Helper functions ------------------

def generate_etag(data_dict):
    """Tạo ETag dựa trên hash MD5 của dữ liệu JSON."""
    data_str = json.dumps(data_dict, sort_keys=True)
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
    response = jsonify({"status": "error", "data": None, "message": message})
    response.headers["Content-Type"] = "application/json"
    return response

# ------------------ Cấu hình OAuth 2.0 Server ------------------
# THÊM MỚI
query_client = create_query_client_func(db.session, OAuth2Client)
save_token = create_save_token_func(db.session, OAuth2Token)
server = AuthorizationServer(
    app,
    query_client=query_client,
    save_token=save_token
)
require_oauth = ResourceProtector()

# Định nghĩa quy trình xác thực (Grant Type)
class MyPasswordGrant(ResourceOwnerPasswordCredentialsGrant):
    def authenticate_user(self, username, password):
        print(f"DEBUG: MyPasswordGrant is trying to authenticate user '{username}'...")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            print(f"DEBUG: User '{username}' authenticated successfully.")
            return user
        print(f"DEBUG: Authentication failed for user '{username}'.")
        return None
class MyBearerTokenValidator(BearerTokenValidator):
    def authenticate_token(self, token_string):
        return OAuth2Token.query.filter_by(access_token=token_string).first()
# Đăng ký Grant Type với server
server.register_grant(MyPasswordGrant)



# Định nghĩa cách Resource Server (API của bạn) xác thực token
def bearer_token_validator(token_string):
    token = OAuth2Token.query.filter_by(access_token=token_string).first()
    if token and not token.is_expired():
        return token

require_oauth.register_token_validator(MyBearerTokenValidator())

# ------------------ OAuth 2.0 Endpoint ------------------
# THÊM MỚI
@app.route('/oauth/token', methods=['POST'])
def issue_token():
    print("\nDEBUG: Received request to /oauth/token")
    print(f"DEBUG: Form data: {request.form.to_dict()}")
    return server.create_token_response()

# ------------------ AUTH ------------------

# Decorator xác thực JWT
def permission_required(required_scope):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = None
            if 'Authorization' in request.headers:
                parts = request.headers['Authorization'].split()
                if len(parts) == 2 and parts[0].lower() == 'bearer':
                    token = parts[1]

            if not token:
                return error_response("Token is missing", 401)

            try:
                data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
                current_user_scopes = data.get('scopes', [])
                if required_scope not in current_user_scopes:
                    return error_response(f"Permission denied: requires '{required_scope}' scope", 403)
                
            except jwt.ExpiredSignatureError:
                return error_response("Token has expired", 401)
            except jwt.InvalidTokenError:
                return error_response("Invalid token", 401)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/api/v1/login', methods=['POST'])
def login():
    body = request.get_json()
    if not body or not body.get('username') or not body.get('password'):
        return error_response("Username and password required", 400)

    username = body.get('username')
    password = body.get('password')
    
    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        # Tổng hợp tất cả các scope từ các role của user
        user_scopes = set()
        user_roles = [role.name for role in user.roles]
        for role in user.roles:
            user_scopes.update(role.scopes.split())

        token = jwt.encode({
            'user': username,
            'roles': user_roles,
            'scopes': list(user_scopes),
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        
        return success_response({"token": token}, "Login successful")

    return error_response("Invalid credentials", 401)

# ------------------ Book API ------------------

@app.route('/api/v1/books', methods=['GET'])
@permission_required('books:read')
def get_books():
    available = request.args.get('available')
    title = request.args.get('title')
    author = request.args.get('author')
    limit = int(request.args.get('limit', 10))
    offset = int(request.args.get('offset', 0))

    query = Book.query

    if available is not None:
        query = query.filter_by(available=(available.lower() == 'true'))
    if title:
        query = query.filter(Book.title.ilike(f"%{title}%"))
    if author:
        query = query.filter(Book.author.ilike(f"%{author}%"))

    total = query.count()
    books = query.offset(offset).limit(limit).all()

    book_list = [b.to_dict() for b in books]
    etag = generate_etag(book_list)

    pagination_info = {
        "total": total,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total else None
    }

    response_data = {"books": book_list, "pagination": pagination_info}
    return success_response(response_data, "Books fetched successfully", etag=etag)


@app.route('/api/v1/books/<int:book_id>', methods=['GET'])
@permission_required('books:read')
def get_book(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return error_response("Book not found", 404)

    book_data = book.to_dict()
    etag = generate_etag(book_data)
    client_etag = request.headers.get('If-None-Match')
    if client_etag == etag:
        return '', 304

    return success_response(book_data, etag=etag)

@app.route('/api/v1/books', methods=['POST'])
@permission_required('books:create')
def create_book():
    data = request.get_json()
    if not data or not data.get('title') or not data.get('author'):
        return error_response("Missing title or author", 400)
    new_book = Book(title=data['title'], author=data['author'])
    db.session.add(new_book)
    db.session.commit()
    book_data = new_book.to_dict()
    etag = generate_etag(book_data)
    return success_response(book_data, "Book created", 201, etag)

@app.route('/api/v1/books/<int:book_id>', methods=['PUT'])
@permission_required('books:update')
def update_book(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return error_response("Book not found", 404)

    data = request.get_json()
    if not data:
        return error_response("No data provided", 400)

    # Cập nhật thông tin cơ bản
    if "title" in data:
        book.title = data["title"]
    if "author" in data:
        book.author = data["author"]

    # Xử lý borrow/return với ràng buộc hợp lệ
    action = "Book info updated"
    if "available" in data:
        new_status = bool(data["available"])

        # Nếu client yêu cầu mượn mà sách đang bị mượn
        if not new_status and not book.available:
            return error_response("Book is already borrowed", 400)

        # Nếu client yêu cầu trả mà sách đang sẵn có
        if new_status and book.available:
            return error_response("Book is already available", 400)

        # Nếu hợp lệ thì cập nhật trạng thái
        if book.available and not new_status:
            book.available = False
            action = "Book borrowed"
        elif not book.available and new_status:
            book.available = True
            action = "Book returned"

    db.session.commit()

    book_data = book.to_dict()
    etag = generate_etag(book_data)
    return success_response(book_data, action, etag=etag)


@app.route('/api/v1/books/<int:book_id>', methods=['DELETE'])
@permission_required('books:delete')
def delete_book(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return error_response("Book not found", 404)
    db.session.delete(book)
    db.session.commit()
    return success_response(None, "Book deleted")

@app.route('/api/v1/books/<int:book_id>/categories', methods=['GET'])
@permission_required('books:read')
def get_categories_for_book(book_id):
    """Lấy tất cả thể loại của một cuốn sách."""
    book = db.session.get(Book, book_id)
    if not book:
        return error_response("Book not found", 404)
        
    categories_list = [c.to_dict() for c in book.categories]
    return success_response(categories_list, f"Categories for book {book_id} fetched")

# ------------------ Category API ------------------

@app.route('/api/v1/categories', methods=['POST'])
@permission_required('categories:create')
def create_category():
    """Tạo một thể loại sách mới."""
    data = request.get_json()
    if not data or not data.get('name'):
        return error_response("Missing category name", 400)

    # Kiểm tra xem thể loại đã tồn tại chưa
    name = data['name']
    if db.session.query(Category).filter_by(name=name).first():
        return error_response("Category already exists", 409) # 409 Conflict

    new_category = Category(name=name)
    db.session.add(new_category)
    db.session.commit()
    
    return success_response(new_category.to_dict(), "Category created", 201)


@app.route('/api/v1/categories', methods=['GET'])
@permission_required('categories:read')
def get_categories():
    """
    Lấy danh sách các thể loại.
    Có thể lọc theo loan_id để lấy các thể loại của cuốn sách trong lượt mượn đó.
    """
    loan_id = request.args.get('loan_id')

    if loan_id:
        # Nếu có loan_id, tìm lượt mượn
        loan = db.session.get(Loan, loan_id)
        if not loan:
            return error_response("Loan not found", 404)
        
        # Từ lượt mượn, tìm sách và lấy các thể loại của nó
        book = loan.book
        if not book:
            return error_response("Book associated with this loan not found", 404)
            
        categories = book.categories
        message = f"Categories for the book in loan {loan_id} fetched"
    else:
        # Nếu không có loan_id, lấy tất cả thể loại
        categories = db.session.query(Category).all()
        message = "All categories fetched"
        
    category_list = [c.to_dict() for c in categories]
    return success_response(category_list, message)

@app.route('/api/v1/categories/<int:category_id>/books', methods=['GET'])
@permission_required('categories:read')
def get_books_in_category(category_id):
    """Lấy danh sách sách trong một thể loại, có hỗ trợ cursor-based pagination."""
    
    # Bước 1: Lấy tham số cursor và limit
    try:
        # Cursor là ID của cuốn sách cuối cùng trong trang trước đó
        cursor = request.args.get('cursor', type=int) 
        limit = request.args.get('limit', default=10, type=int)
    except (TypeError, ValueError):
        return error_response("Invalid pagination parameters", 400)

    # Tìm thể loại
    category = db.session.get(Category, category_id)
    if not category:
        return error_response("Category not found", 404)
        
    # Bước 2: Xây dựng query
    # Bắt đầu với query cơ bản để lấy sách trong category này
    query = Book.query.with_parent(category, 'books')
    
    # Nếu có cursor, chỉ lấy các sách có ID lớn hơn cursor
    if cursor:
        query = query.filter(Book.id > cursor)
    
    # Luôn sắp xếp theo ID và giới hạn số lượng kết quả
    books_on_page = query.order_by(Book.id.asc()).limit(limit).all()
    
    # Bước 3: Xác định next_cursor
    next_cursor = None
    if books_on_page:
        # next_cursor là ID của cuốn sách cuối cùng trong danh sách vừa lấy
        next_cursor = books_on_page[-1].id
        
    book_list = [b.to_dict() for b in books_on_page]
    
    # Bước 4: Xây dựng cấu trúc response
    pagination_meta = {
        "next_cursor": next_cursor,
        "count": len(book_list)
    }

    response_data = {
        "books": book_list,
        "pagination": pagination_meta
    }
    
    return success_response(response_data, f"Books in category '{category.name}' fetched successfully")
# ------------------ Member API ------------------

@app.route('/api/v1/members', methods=['GET'])
@permission_required('members:read')
def get_members():
    name = request.args.get('name')
    limit = int(request.args.get('limit', 10))
    offset = int(request.args.get('offset', 0))

    query = Member.query
    if name:
        query = query.filter(Member.name.ilike(f"%{name}%"))

    total = query.count()
    members = query.offset(offset).limit(limit).all()

    data = [m.to_dict() for m in members]
    pagination = {
        "total": total,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total else None
    }
    return success_response({"members": data, "pagination": pagination})

@app.route('/api/v1/members/<int:member_id>/loans', methods=['GET'])
@permission_required('members:read')
def get_loans_for_member(member_id):
    """Lấy tất cả các lượt mượn của một thành viên cụ thể với pagination."""
    
    try:
        page = int(request.args.get('page', 1))
        # Thay đổi 'per_page' thành 'page_size'
        page_size = int(request.args.get('page_size', 20)) 
    except (TypeError, ValueError):
        return error_response("Invalid pagination parameters", 400)

    member = db.session.get(Member, member_id)
    if not member:
        return error_response("Member not found", 404)

    # Cập nhật tham số `per_page` của hàm paginate()
    pagination_obj = db.session.query(Loan).filter_by(member_id=member_id).paginate(
        page=page, per_page=page_size, error_out=False
    )
    
    loans_on_page = pagination_obj.items
    
    loan_list = [l.to_dict() for l in loans_on_page]
    
    pagination_meta = {
        "page": pagination_obj.page,
        # Thay đổi key trong response cho nhất quán
        "page_size": pagination_obj.per_page, 
        "total_pages": pagination_obj.pages,
        "total_items": pagination_obj.total,
        "has_next": pagination_obj.has_next,
        "has_prev": pagination_obj.has_prev
    }

    response_data = {
        "loans": loan_list,
        "pagination": pagination_meta
    }

    return success_response(response_data, f"Loans for member {member_id} fetched successfully")

# ------------------ Loan API ------------------

@app.route('/api/v1/loans', methods=['POST'])
@permission_required('loans:create')
def create_loan():
    data = request.get_json()
    member_id = data.get('member_id')
    book_id = data.get('book_id')

    if not member_id or not book_id:
        return error_response("Missing member_id or book_id", 400)

    book = db.session.get(Book, book_id)
    if not book or not book.available:
        return error_response("Book not available", 400)

    new_loan = Loan(member_id=member_id, book_id=book_id)
    book.available = False

    db.session.add(new_loan)
    db.session.commit()
    return success_response(new_loan.to_dict(), "Loan created", 201)

@app.route('/api/v1/loans/<int:loan_id>/books', methods=['GET'])
@permission_required('loans:read')
def get_book_for_loan(loan_id):
    """
    Lấy thông tin sách từ một lượt mượn cụ thể.
    Lưu ý: Endpoint này trả về một đối tượng Book duy nhất.
    """
    
    # Tìm lượt mượn (loan) dựa trên loan_id
    loan = db.session.get(Loan, loan_id)
    
    if not loan:
        return error_response("Loan not found", 404)
        
    # Lấy thông tin sách liên quan thông qua relationship
    book = loan.book
    
    if not book:
        # Trường hợp hiếm gặp, dữ liệu không nhất quán
        return error_response("Book associated with this loan not found", 404)
        
    return success_response(book.to_dict(), "Book for the specified loan fetched successfully")

# ------------------ Singleton Resource: Statistic ------------------

@app.route('/api/v1/statistic', methods=['GET'])
@require_oauth('statistics:read')
def get_library_statistic():
    """
    Lấy thông tin thống kê tổng quan của thư viện.
    Đây là một ví dụ về Singleton Resource vì chỉ có MỘT bộ thống kê
    cho toàn bộ hệ thống, không có ID.
    """
    try:
        total_books = db.session.query(Book).count()
        total_members = db.session.query(Member).count()
        
        # Đếm số sách đang bị mượn (available = False)
        borrowed_books = db.session.query(Book).filter_by(available=False).count()

        # Tạo đối tượng dữ liệu để trả về
        statistic_data = {
            "total_books": total_books,
            "total_members": total_members,
            "borrowed_books": borrowed_books,
            "available_books": total_books - borrowed_books
        }
        
        return success_response(statistic_data, "Library statistic fetched successfully")

    except Exception as e:
        # Ghi lại lỗi ra console để debug nếu cần
        print(f"Error fetching statistic: {e}")
        return error_response("Could not retrieve statistic", 500)
    
# ------------------ Swagger UI ------------------

# Đường dẫn file swagger.yaml trong thư mục static
SWAGGER_URL = '/docs'
API_URL = '/static/swagger.yaml'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={'app_name': "Book Management API"}
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Route để phục vụ swagger.yaml từ thư mục static
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

@app.route('/')
def home():
    return 'Swagger UI available at /docs'

def setup_initial_data():
    """Tạo roles và user admin mặc định nếu chưa có."""
    # Tạo roles
    admin_role = Role.query.filter_by(name='admin').first()
    if not admin_role:
        admin_scopes = ' '.join([
            'books:read', 'books:create', 'books:update', 'books:delete',
            'categories:read', 'categories:create',
            'members:read', 'members:create',
            'loans:read', 'loans:create',
            'statistics:read'
        ])
        admin_role = Role(name='admin', scopes=admin_scopes)
        db.session.add(admin_role)

    member_role = Role.query.filter_by(name='member').first()
    if not member_role:
        member_scopes = ' '.join(['books:read', 'categories:read', 'loans:read'])
        member_role = Role(name='member', scopes=member_scopes)
        db.session.add(member_role)
    
    # Tạo user admin
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        admin_user = User(username='admin')
        admin_user.set_password('123456')
        admin_user.roles.append(admin_role)
        db.session.add(admin_user)

    # THÊM MỚI: Tạo một OAuth Client mẫu
    client = OAuth2Client.query.filter_by(client_id='my-web-app').first()
    if not client:
        print("Creating default OAuth2 client...")
        client = OAuth2Client(
            client_id='my-web-app',
            client_secret='super-secret-for-app',
            client_name='My Web App',
            grant_types='password',
            response_types='token',
            scope=' '.join([ # Các scope mà client này được phép yêu cầu
                'books:read', 'books:create', 'books:update', 'books:delete',
                'categories:read', 'categories:create',
                'members:read',
                'loans:read', 'loans:create',
                'statistics:read'
            ]),
            token_endpoint_auth_method='client_secret_post client_secret_basic'
        )
        db.session.add(client) 
    db.session.commit()

# ------------------ Main ------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        setup_initial_data()
    app.run(debug=True, port=5001)
