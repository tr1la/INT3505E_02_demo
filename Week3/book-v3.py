from flask import Flask, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import hashlib
import json
import jwt
import datetime
from functools import wraps

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:240724@localhost/soa_demo'
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

# ------------------ Helper functions ------------------

def success_response(data=None, message=None, status_code=200):
    response = make_response(jsonify({
        "status": "success",
        "data": data,
        "message": message
    }), status_code)
    response.headers["Content-Type"] = "application/json"
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
    query = Book.query
    if available is not None:
        query = query.filter_by(available=(available.lower() == 'true'))
    books = query.all()
    book_list = [b.to_dict() for b in books]
  
    return success_response(book_list)

@app.route('/api/v1/books/<int:book_id>', methods=['GET'])
@token_required
def get_book(current_user, book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return error_response("Book not found", 404)

    book_data = book.to_dict()

    return success_response(book_data)

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
    return success_response(book_data, "Book created", 201)


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
  
    return success_response(book_data, action)


@app.route('/api/v1/books/<int:book_id>', methods=['DELETE'])
@token_required
def delete_book(current_user, book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return error_response("Book not found", 404)
    db.session.delete(book)
    db.session.commit()
    return success_response(None, "Book deleted")



# ------------------ Main ------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
