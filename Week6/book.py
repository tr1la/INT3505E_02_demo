from flask import Flask, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import hashlib
import json
import jwt
import datetime
from functools import wraps
from flask_swagger_ui import get_swaggerui_blueprint
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

# ------------------ AUTH ------------------

# Decorator xác thực JWT
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

@app.route('/api/v1/login', methods=['POST'])
def login():
    body = request.get_json()
    username = body.get('username')
    password = body.get('password')
    if username == 'admin' and password == '123456':  # Demo
        token = jwt.encode({
            'user': username,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        return success_response({"token": token}, "Login successful")
    return error_response("Invalid credentials", 401)

# ------------------ Book API ------------------

@app.route('/api/v1/books', methods=['GET'])
@token_required
def get_books(current_user):
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
@token_required
def get_book(current_user, book_id):
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
@token_required
def create_book(current_user):
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
@token_required
def update_book(current_user, book_id):
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
@token_required
def delete_book(current_user, book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return error_response("Book not found", 404)
    db.session.delete(book)
    db.session.commit()
    return success_response(None, "Book deleted")

@app.route('/api/v1/books/<int:book_id>/categories', methods=['GET'])
@token_required
def get_categories_for_book(current_user, book_id):
    """Lấy tất cả thể loại của một cuốn sách."""
    book = db.session.get(Book, book_id)
    if not book:
        return error_response("Book not found", 404)
        
    categories_list = [c.to_dict() for c in book.categories]
    return success_response(categories_list, f"Categories for book {book_id} fetched")

# ------------------ Category API ------------------

@app.route('/api/v1/categories', methods=['POST'])
@token_required
def create_category(current_user):
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
@token_required
def get_categories(current_user):
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
@token_required
def get_books_in_category(current_user, category_id):
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
@token_required
def get_members(current_user):
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
@token_required
def get_loans_for_member(current_user, member_id):
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
@token_required
def create_loan(current_user):
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
@token_required
def get_book_for_loan(current_user, loan_id):
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
@token_required
def get_library_statistic(current_user):
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

# ------------------ Main ------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
