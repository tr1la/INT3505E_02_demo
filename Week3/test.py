import hashlib
import json
import asyncio

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from datetime import datetime, timezone
from typing import Dict, Any, List, Annotated


app = FastAPI(title="Group 2 - Cacheble RESTful API Demo")

BOOKS: Dict[int, Dict[str, Any]] = {
    1: {"id": 1, "title": "Book 1", "status": "available", "updated_at": datetime.now(timezone.utc)},
    2: {"id": 2, "title": "Book 2", "status": "borrowed", "updated_at": datetime.now(timezone.utc)},
    3: {"id": 3, "title": "Book 3", "status": "available", "updated_at": datetime.now(timezone.utc)},
}
LOCK = asyncio.Lock()

def make_etag(payload: Any) -> str:
    raw = json.dumps(payload, default=str, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.md5(raw).hexdigest() 
    return f"\"{digest}\""

@app.get("/books")
async def list_books():
    data: List[Dict[str, Any]] = [
        {"id": b["id"], "title": b["title"], "status": b["status"]} for b in BOOKS.values()
    ]
    etag = make_etag(data)

    resp = JSONResponse(content=data)
    resp.headers["Cache-Control"] = "public, max-age=600, must-revalidate"
    resp.headers["ETag"] = etag
    return resp

@app.get("/books/{book_id}")
async def book_detail(book_id: int, request: Request,  if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None):
    book = BOOKS.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    etag = make_etag(book)
    inm = request.headers.get("If-None-Match")

    if inm and inm.strip() == etag:
        return Response(status_code=304, headers={
            "ETag": etag,
            "Cache-Control": "no-cache",
        })

    resp = JSONResponse(content=jsonable_encoder(book))
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.post("/books/{book_id}/borrow")
async def borrow(book_id: int):
    async with LOCK:
        book = BOOKS.get(book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        if book["status"] == "borrowed":
            raise HTTPException(status_code=409, detail="Already borrowed")
        book["status"] = "borrowed"
        book["updated_at"] = datetime.now(timezone.utc)
        return {"message": "Borrowed", "book": book}

@app.post("/books/{book_id}/return")
async def return_book(book_id: int):
    async with LOCK:
        book = BOOKS.get(book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        if book["status"] == "available":
            raise HTTPException(status_code=409, detail="Already available")
        book["status"] = "available"
        book["updated_at"] = datetime.now(timezone.utc)
        return {"message": "Returned", "book": book}
##uvicorn app:app --reload --port 5001
