from datetime import datetime
from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T | None = None
    request_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class PaginatedResponse(BaseModel, Generic[T]):
    page: int = 1
    page_size: int = 20
    total: int = 0
    items: list[T] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    code: int
    message: str
    detail: str = ""