from __future__ import annotations


class DomainError(Exception):
    """Business failure translated to HTTP only at the application boundary."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
