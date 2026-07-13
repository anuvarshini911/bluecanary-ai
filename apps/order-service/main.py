"""
order-service — sample app for BlueCanary AI (S2-P-10)
Blue-Green strategy target.

Exposes:
  GET /healthz    - liveness/readiness probe
  GET /metrics    - Prometheus scrape endpoint
  GET /orders     - primary business endpoint
  GET /version    - reports app version (used to prove blue/green cutover in demos)
"""

import os
import random
import time

from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

APP_VERSION = os.getenv("APP_VERSION", "v1")
INJECT_FAILURE = os.getenv("INJECT_FAILURE", "false").lower() == "true"

app = FastAPI(title="order-service", version=APP_VERSION)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request latency in seconds",
    ["endpoint"],
)


@app.middleware("http")
async def record_metrics(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    REQUEST_LATENCY.labels(endpoint=request.url.path).observe(duration)
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
    ).inc()
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/version")
def version():
    return {"version": APP_VERSION}


@app.get("/orders")
def get_orders():
    if INJECT_FAILURE and random.random() < 0.3:
        REQUEST_COUNT.labels(method="GET", endpoint="/orders", status=500).inc()
        return Response(status_code=500, content="internal error (injected)")

    if INJECT_FAILURE:
        time.sleep(random.uniform(0.3, 0.6))

    return {
        "orders": [
            {"id": 1, "item": "widget", "qty": 3},
            {"id": 2, "item": "gadget", "qty": 1},
        ],
        "served_by_version": APP_VERSION,
    }


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
