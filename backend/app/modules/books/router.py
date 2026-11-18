from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import UowDep
from backend.app.core.security import owner
from backend.app.modules.books.schemas import BookInput, BookResponse
from backend.app.modules.books.service import BookService

router = APIRouter(tags=["books"], dependencies=[Depends(owner)])


@router.get("/books", operation_id="listBooks", response_model=list[BookResponse])
def list_books(uow: UowDep) -> list[BookResponse]:
    return BookService(uow).list()


@router.post("/books", operation_id="createBook", response_model=BookResponse, status_code=201)
def create_book(body: BookInput, uow: UowDep) -> BookResponse:
    return BookService(uow).create(body)
