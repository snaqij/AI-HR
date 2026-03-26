"""统一响应封装定义。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

DataT = TypeVar("DataT")


class ErrorPayload(BaseModel):
    """标准化接口错误结构。"""

    code: str
    message: str


class Envelope(BaseModel, Generic[DataT]):
    """所有 API 使用的统一响应信封。"""

    model_config = ConfigDict(populate_by_name=True)

    ok: bool
    schema_version: str = "1"
    data: DataT | None = None
    error: ErrorPayload | None = None

    @classmethod
    def success(cls, data: DataT) -> "Envelope[DataT]":
        """构造成功响应。"""
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, code: str, message: str) -> "Envelope[None]":
        """构造失败响应。"""
        return cls(ok=False, error=ErrorPayload(code=code, message=message))
