"""
AI Gate — BlueCanary AI (S2-P-10), Deliverable D-05.

Sits between the deployment pipeline and the promote/rollback decision.
Pulls live health metrics from Prometheus for a given service, then:
  AI-1 (Groq, fast):    quick healthy/risky/unhealthy classification
  AI-2 (Gemini):        plain-English rationale for the decision

Exposes:
  POST /evaluate   { "service": "order-service-preview" } -> decision + rationale
  GET  /healthz
"""

import os
import json

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq
import google.generativeai as genai

load_dotenv()

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GROQ_API_KEY or not GEMINI_API_KEY:
    raise RuntimeError("GROQ_API_KEY and GEMINI_API_KEY must be set (see .env)")

groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-3.6-flash")

app = FastAPI(title="AI Gate", version="0.1")


class EvaluateRequest(BaseModel):
    service: str  # e.g. "order-service-preview"


class EvaluateResponse(BaseModel):
    service: str
    metrics: dict
    ai1_classification: str
    ai1_confidence: str
    decision: str  # "promote" | "rollback"
    rationale: str


def query_prometheus(promql: str) -> float:
    """Run an instant PromQL query, return the first scalar result (or 0.0)."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": promql},
            timeout=5,
        )
        resp.raise_for_status()
        result = resp.json()["data"]["result"]
        if not result:
            return 0.0
        return float(result[0]["value"][1])
    except Exception:
        return 0.0


def fetch_metrics(service: str) -> dict:
    error_rate = query_prometheus(
        f'sum(rate(http_requests_total{{service="{service}",status=~"5.."}}[1m])) '
        f'/ sum(rate(http_requests_total{{service="{service}"}}[1m])) or on() vector(0)'
    )
    p95_latency = query_prometheus(
        f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket'
        f'{{service="{service}"}}[1m])) by (le)) or on() vector(0)'
    )
    request_rate = query_prometheus(
        f'sum(rate(http_requests_total{{service="{service}"}}[1m])) or on() vector(0)'
    )
    return {
        "error_rate": round(error_rate, 4),
        "p95_latency_seconds": round(p95_latency, 4),
        "request_rate_per_sec": round(request_rate, 4),
    }


def classify_with_groq(metrics: dict) -> tuple[str, str]:
    """AI-1: fast pass/fail-style classification. Returns (classification, confidence)."""
    prompt = (
        "You are a deployment health classifier for a Kubernetes blue-green rollout. "
        "Given these live metrics for the PREVIEW (candidate) version, classify the "
        "deployment as exactly one of: healthy, risky, unhealthy.\n\n"
        f"Metrics:\n{json.dumps(metrics, indent=2)}\n\n"
        "Guidance: error_rate is a fraction (0.05 = 5%). Above 0.10 is generally unhealthy. "
        "p95_latency_seconds above 1.0s is concerning. Low request_rate means low sample "
        "confidence.\n\n"
        'Respond ONLY as JSON: {"classification": "healthy|risky|unhealthy", '
        '"confidence": "low|medium|high"}'
    )
    for attempt in range(2):  # one retry, since Groq occasionally returns an empty generation
        try:
            resp = groq_client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=150,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content.strip()
            print(f"[DEBUG] Groq raw response (attempt {attempt+1}): {raw!r}")
            if not raw:
                continue
            raw_clean = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw_clean)
            return data.get("classification", "unhealthy"), data.get("confidence", "low")
        except Exception as e:
            print(f"[DEBUG] Groq call/parse failed (attempt {attempt+1}): {e}")
            continue
    return "unhealthy", "low"


def explain_with_gemini(service: str, metrics: dict, classification: str) -> str:
    """AI-2: plain-English rationale for the promote/rollback decision."""
    prompt = (
        f"A Kubernetes blue-green deployment gate just classified the preview version "
        f"of '{service}' as '{classification}' based on these live metrics:\n"
        f"{json.dumps(metrics, indent=2)}\n\n"
        "Write a short (2-3 sentence) plain-English explanation of this decision for "
        "an engineer reviewing the deployment. Be specific about which metric(s) drove "
        "the decision and what a reasonable next step is."
    )
    try:
        resp = gemini_model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        return f"(Gemini rationale unavailable: {e})"


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest):
    metrics = fetch_metrics(req.service)
    classification, confidence = classify_with_groq(metrics)
    decision = "promote" if classification == "healthy" else "rollback"
    rationale = explain_with_gemini(req.service, metrics, classification)

    return EvaluateResponse(
        service=req.service,
        metrics=metrics,
        ai1_classification=classification,
        ai1_confidence=confidence,
        decision=decision,
        rationale=rationale,
    )
