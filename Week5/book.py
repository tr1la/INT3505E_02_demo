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
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    available = db.Column(db.Boolean, default=True)

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
