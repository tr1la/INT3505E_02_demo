from flask import Flask, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import hashlib
import json

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:240724@localhost/soa_demo'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    return response


def error_response(message, status_code=400):
    return jsonify({"status": "error", "data": None, "message": message}), status_code

# ------------------ Book API ------------------

@app.route('/books', methods=['GET'])
def get_books():
    available = request.args.get('available')
    query = Book.query
    if available is not None:
        query = query.filter_by(available=(available.lower() == 'true'))
    books = query.all()
    book_list = [b.to_dict() for b in books]

    return success_response(book_list)


@app.route('/books/<int:book_id>', methods=['GET'])
def get_book(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return error_response("Book not found", 404)

    book_data = book.to_dict()


    return success_response(book_data)

@app.route('/books', methods=['POST'])
def create_book():
    data = request.get_json()
    if not data or not data.get('title') or not data.get('author'):
        return error_response("Missing title or author", 400)
    new_book = Book(title=data['title'], author=data['author'])
    db.session.add(new_book)
    db.session.commit()
    book_data = new_book.to_dict()
    return success_response(book_data, "Book created", 201)

@app.route('/books/<int:book_id>', methods=['PUT'])
def update_book(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return error_response("Book not found", 404)

    data = request.get_json()
    if "title" in data:
        book.title = data["title"]
    if "author" in data:
        book.author = data["author"]
    if "available" in data:
        book.available = bool(data["available"])
    db.session.commit()

    book_data = book.to_dict()
    return success_response(book_data, "Book updated")

@app.route('/books/<int:book_id>', methods=['DELETE'])
def delete_book(book_id):
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
