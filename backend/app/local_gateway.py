"""Narrow local HTTP gateway for the internal incident ingest endpoint."""

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response


BACKEND_INGEST_URL = "http://127.0.0.1:8000/api/internal/incidents"
UPSTREAM_TIMEOUT_SECONDS = 5.0
INGEST_PATH = "/api/internal/incidents"

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.api_route("/{path:path}", methods=["POST"])
async def proxy_post(request: Request, path: str) -> Response:
    if request.url.path != INGEST_PATH:
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    token = request.headers.get("X-Internal-Token")
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    body = await request.body()
    headers = {"X-Internal-Token": token}
    content_type = request.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type

    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS) as client:
            upstream = await client.post(BACKEND_INGEST_URL, content=body, headers=headers)
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"detail": "Backend request timed out"})
    except httpx.RequestError:
        return JSONResponse(status_code=502, content={"detail": "Backend unavailable"})

    response_headers = {}
    upstream_content_type = upstream.headers.get("content-type")
    if upstream_content_type:
        response_headers["content-type"] = upstream_content_type
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
