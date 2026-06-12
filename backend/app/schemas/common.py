"""Shared response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class Message(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    trace_id: str | None = None
