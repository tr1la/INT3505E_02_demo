// server.js
const express = require("express");
const crypto = require("crypto");
const app = express();

app.use(express.json());

let books = [
  { id: 1, title: "Clean Code", status: "available" },
  { id: 2, title: "Domain-Driven Design", status: "available" },
  { id: 3, title: "You Don't Know JS", status: "available" },
];

function computeEtag(obj) {
  const body = JSON.stringify(obj);
  return `"${crypto.createHash("sha1").update(body).digest("hex")}"`;
}

// GET /books
app.get("/books", (req, res) => {
  const payload = { books };
  const etag = computeEtag(payload);

  // Cho phép cache 10 phút nhưng luôn revalidate
  res.set("Cache-Control", "public, max-age=600, must-revalidate");
  res.set("ETag", etag);

  if (req.headers["if-none-match"] === etag) {
    return res.status(304).end();
  }

  res.json(payload);
});

// POST /books/:id/borrow
app.post("/books/:id/borrow", (req, res) => {
  const id = Number(req.params.id);
  const book = books.find((x) => x.id === id);

  if (!book) return res.status(404).json({ error: "Not found" });
  if (book.status === "borrowed")
    return res.status(400).json({ error: "Already borrowed" });

  book.status = "borrowed";
  res.json({ ok: true, book });
});

app.listen(3000, () =>
  console.log("Node.js server running at http://127.0.0.1:3000")
);
