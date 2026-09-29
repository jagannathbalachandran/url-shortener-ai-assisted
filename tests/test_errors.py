"""Unit tests for the standard error-shape helpers."""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from shortener.errors import (
    ErrorDetail,
    build_error_body,
    error_response,
    register_exception_handlers,
)


def test_build_error_body_without_details() -> None:
    body = build_error_body("not_found", "No link found for the given code.")

    assert body == {
        "error": {"code": "not_found", "message": "No link found for the given code."}
    }


def test_build_error_body_with_details() -> None:
    details: list[ErrorDetail] = [{"loc": ["body", "url"], "msg": "field required"}]

    body = build_error_body("validation_error", "Request validation failed.", details)

    error = body["error"]
    assert isinstance(error, dict)
    assert error["details"] == details


def test_error_response_sets_status_and_body() -> None:
    response = error_response(404, "not_found", "No link found for the given code.")

    assert response.status_code == 404
    assert json.loads(bytes(response.body)) == {
        "error": {"code": "not_found", "message": "No link found for the given code."}
    }


def test_error_response_carries_headers() -> None:
    response = error_response(
        429, "rate_limited", "Rate limit exceeded.", headers={"Retry-After": "30"}
    )

    assert response.headers["retry-after"] == "30"


def test_http_exception_with_uncommon_status_maps_to_generic_code() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/teapot")
    def _teapot() -> None:
        raise HTTPException(status_code=418, detail="I'm a teapot")

    client = TestClient(app)
    response = client.get("/teapot")

    assert response.status_code == 418
    body = response.json()
    assert body["error"]["code"] == "http_error"
    assert body["error"]["message"] == "I'm a teapot"
