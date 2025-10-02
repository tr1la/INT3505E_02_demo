import sqlite3, os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_PATH = "library.db"


# DB 

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS books(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT NOT NULL,
        total_copies INTEGER NOT NULL DEFAULT 1,
        available_copies INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS loans(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        borrowed_at TEXT NOT NULL,
        due_at TEXT NOT NULL,
        returned_at TEXT,
        FOREIGN KEY(book_id) REFERENCES books(id)
    )""")
    conn.commit()
    conn.close()

init_db()

def now_iso():
    return datetime.utcnow().isoformat() + "Z"


# Books

@app.get("/health")
def health():
    return {"status": "ok", "time": now_iso()}

@app.post("/books")
def create_book():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    author = (data.get("author") or "").strip()
    total = data.get("total_copies", 1)

    if not title or not author:
        return jsonify({"error": "Thiếu title/author"}), 422
    try:
        total = int(total)
        assert total >= 1
    except Exception:
        return jsonify({"error": "total_copies phải là số nguyên >= 1"}), 422

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO books(title, author, total_copies, available_copies, created_at) VALUES(?,?,?,?,?)",
        (title, author, total, total, now_iso()),
    )
    conn.commit()
    book_id = cur.lastrowid
    book = cur.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    conn.close()
    return jsonify(dict(book)), 201

@app.get("/books")
def list_books():
    q = (request.args.get("q") or "").strip()
    conn = get_db()
    cur = conn.cursor()
    if q:
        like = f"%{q}%"
        rows = cur.execute(
            "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? ORDER BY id DESC",
            (like, like),
        ).fetchall()
    else:
        rows = cur.execute("SELECT * FROM books ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.get("/books/<int:book_id>")
def get_book(book_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Không tìm thấy sách"}), 404
    return jsonify(dict(row))

@app.put("/books/<int:book_id>")
def update_book(book_id):
    data = request.get_json(silent=True) or {}
    conn = get_db()
    cur = conn.cursor()
    book = cur.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    if not book:
        conn.close()
        return jsonify({"error": "Không tìm thấy sách"}), 404

    title = (data.get("title") or book["title"]).strip()
    author = (data.get("author") or book["author"]).strip()
    new_total = data.get("total_copies", book["total_copies"])

    try:
        new_total = int(new_total)
        assert new_total >= 1
    except Exception:
        conn.close()
        return jsonify({"error": "total_copies phải là số nguyên >= 1"}), 422

    # cập nhật available theo total mới (không vượt quá total và không âm)
    delta = new_total - book["total_copies"]
    new_available = max(0, min(new_total, book["available_copies"] + delta))

    cur.execute(
        "UPDATE books SET title=?, author=?, total_copies=?, available_copies=? WHERE id=?",
        (title, author, new_total, new_available, book_id),
    )
    conn.commit()
    updated = cur.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    conn.close()
    return jsonify(dict(updated))

@app.delete("/books/<int:book_id>")
def delete_book(book_id):
    conn = get_db()
    cur = conn.cursor()
    # chặn xoá nếu còn lượt mượn chưa trả
    active = cur.execute(
        "SELECT COUNT(*) AS c FROM loans WHERE book_id=? AND returned_at IS NULL",
        (book_id,),
    ).fetchone()["c"]
    if active > 0:
        conn.close()
        return jsonify({"error": "Không thể xoá: còn lượt mượn đang hoạt động"}), 409
    cur.execute("DELETE FROM books WHERE id=?", (book_id,))
    conn.commit()
    conn.close()
    return "", 204


# Borrow / Return

DEFAULT_DAYS = 14

@app.post("/borrow")
def borrow():
    """
    Body JSON: { "book_id": 1, "days": 14 }
    - Giảm available_copies nếu còn sách.
    - Tạo loan với due_at = now + days.
    """
    data = request.get_json(silent=True) or {}
    book_id = data.get("book_id")
    days = data.get("days", DEFAULT_DAYS)

    try:
        book_id = int(book_id)
        days = int(days)
        assert days >= 1
    except Exception:
        return jsonify({"error": "book_id và days phải là số hợp lệ; days >= 1"}), 422

    conn = get_db()
    cur = conn.cursor()
    book = cur.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    if not book:
        conn.close()
        return jsonify({"error": "Không tìm thấy sách"}), 404
    if book["available_copies"] <= 0:
        conn.close()
        return jsonify({"error": "Hết sách để mượn"}), 409

    borrowed_at = datetime.utcnow()
    due_at = borrowed_at + timedelta(days=days)

    cur.execute(
        "INSERT INTO loans(book_id, borrowed_at, due_at, returned_at) VALUES(?,?,?,NULL)",
        (book_id, borrowed_at.isoformat() + "Z", due_at.isoformat() + "Z"),
    )
    cur.execute(
        "UPDATE books SET available_copies = available_copies - 1 WHERE id=?",
        (book_id,),
    )
    conn.commit()
    loan_id = cur.lastrowid
    loan = cur.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
    conn.close()
    return jsonify(dict(loan)), 201

@app.post("/return")
def return_book():
    """
    Body JSON: { "loan_id": 123 }
    - Đánh dấu returned_at và tăng available_copies.
    """
    data = request.get_json(silent=True) or {}
    loan_id = data.get("loan_id")
    try:
        loan_id = int(loan_id)
    except Exception:
        return jsonify({"error": "loan_id không hợp lệ"}), 422

    conn = get_db()
    cur = conn.cursor()
    loan = cur.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
    if not loan:
        conn.close()
        return jsonify({"error": "Không tìm thấy lượt mượn"}), 404
    if loan["returned_at"] is not None:
        conn.close()
        return jsonify({"error": "Lượt mượn này đã được trả trước đó"}), 409

    cur.execute(
        "UPDATE loans SET returned_at=? WHERE id=?",
        (now_iso(), loan_id),
    )
    cur.execute(
        "UPDATE books SET available_copies = available_copies + 1 WHERE id=?",
        (loan["book_id"],),
    )
    conn.commit()
    updated = cur.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
    conn.close()
    return jsonify(dict(updated))

# Xem danh sách lượt mượn đang hoạt động — hữu ích để kiểm tra
@app.get("/loans")
def list_loans():
    status = (request.args.get("status") or "").lower()
    conn = get_db()
    cur = conn.cursor()
    if status == "active":
        rows = cur.execute(
            "SELECT * FROM loans WHERE returned_at IS NULL ORDER BY id DESC"
        ).fetchall()
    else:
        rows = cur.execute("SELECT * FROM loans ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(debug=True)

#create book
"""curl -X POST http://localhost:5000/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Clean Code","author":"Robert C. Martin","total_copies":3}'"""
#borrow book
"""curl -X POST http://localhost:5000/borrow \
  -H "Content-Type: application/json" \
  -d '{"book_id":1,"days":7}'
"""
#return book
"""curl -X POST http://localhost:5000/return \
  -H "Content-Type: application/json" \
  -d '{"loan_id":1}'
"""
#get book
"""curl -X GET http://localhost:5000/books/1"""
#get list book
"""curl -X GET http://localhost:5000/books"""
#delete book
"""curl -X DELETE http://localhost:5000/books/1"""
#update book
"""curl -X PUT http://localhost:5000/books/1 \
  -H "Content-Type: application/json" \
  -d '{"title":"Clean Code - Updated","author":"Robert C. Martin","total_copies":5}'"""
#get list loan
"""curl -X GET http://localhost:5000/loans"""
