"""
payment-gateway — second service for BlueCanary AI (S2-P-10).

A distinct microservice (separate from order-service) demonstrating the
platform works across multiple services, not just one. Same
observability contract (Prometheus metrics) as order-service so the
existing AnalysisTemplates and AI Gate work against it unmodified.
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

app = FastAPI(title="payment-gateway", version=APP_VERSION)

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


@app.post("/charge")
def charge():
    if INJECT_FAILURE and random.random() < 0.3:
        REQUEST_COUNT.labels(method="POST", endpoint="/charge", status=500).inc()
        return Response(status_code=500, content="internal error (injected)")

    if INJECT_FAILURE:
        time.sleep(random.uniform(0.3, 0.6))

    return {
        "transaction_id": f"txn_{random.randint(100000, 999999)}",
        "status": "approved",
        "amount": 49.99,
        "served_by_version": APP_VERSION,
    }


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
