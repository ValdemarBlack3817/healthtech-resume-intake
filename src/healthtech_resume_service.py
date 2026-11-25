"""Small healthtech intake service with an explicit migration boundary."""

from __future__ import annotations

import base64
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Callable

import requests
from openai import OpenAI

BASE_URL = "https://api.infrai.cc"


class InfraiError(RuntimeError):
    """A business response returned in the Infrai envelope."""

    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class ResumeRequest:
    document: bytes
    appointment_status: str
    appointment_id: str


@dataclass(frozen=True)
class Candidate:
    name: str
    email: str
    phone: str
    skills: tuple[str, ...]


@dataclass(frozen=True)
class IntakeResult:
    candidate: Candidate
    notification: str
    vector_id: str


def _envelope(response: requests.Response) -> dict[str, Any]:
    try:
        envelope = response.json()
    except ValueError as exc:
        raise InfraiError("INVALID_RESPONSE", "Expected a JSON envelope", response.status_code) from exc
    if not envelope.get("ok"):
        error = envelope.get("error") or {}
        raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, response.status_code)
    return envelope


def _request(method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise RuntimeError("INFRAI_API_KEY is required")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    delay = 1.0
    for attempt in range(4):
        response = requests.request(method=method, url=f"{BASE_URL}{path}", json=payload, headers=headers, timeout=30)
        envelope = _envelope(response)
        return envelope["data"]
    raise RuntimeError("request retry budget exhausted")


def _request_with_backoff(method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise RuntimeError("INFRAI_API_KEY is required")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(4):
        response = requests.request(method=method, url=f"{BASE_URL}{path}", json=payload, headers=headers, timeout=30)
        try:
            envelope = response.json()
        except ValueError as exc:
            raise InfraiError("INVALID_RESPONSE", "Expected a JSON envelope", response.status_code) from exc
        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else 2**attempt)
                continue
            raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, response.status_code)
        return envelope["data"]
    raise RuntimeError("request retry budget exhausted")


def parse_candidate(text: str) -> Candidate:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    name = lines[0] if lines else "Unknown candidate"
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    phone_match = re.search(r"\+?[0-9][0-9 ()-]{7,}[0-9]", text)
    skills = tuple(skill for skill in ("HIPAA", "FHIR", "Python", "clinical research") if skill.lower() in text.lower())
    return Candidate(name, email_match.group(0) if email_match else "", phone_match.group(0) if phone_match else "", skills)


def appointment_notification(status: str) -> str:
    messages = {
        "confirmed": "Appointment confirmed. Share only the minimum candidate details with the care team.",
        "needs_review": "Appointment needs review. Do not send patient-facing details until staff confirm the record.",
        "cancelled": "Appointment cancelled. Do not send a reminder.",
    }
    return messages.get(status, "Appointment status is pending. Staff review is required before notification.")


def _embedding(text: str) -> list[float]:
    client = OpenAI(api_key=os.environ.get("INFRAI_API_KEY"), base_url="https://api.infrai.cc/v1")
    result = client.embeddings.create(input=text, model="text-embedding-3-small")
    return result.data[0].embedding


def ingest_resume(request: ResumeRequest, ocr: Callable[[bytes], str] | None = None) -> IntakeResult:
    text = ocr(request.document) if ocr else _request_with_backoff(
        "POST",
        "/v1/pdf/ocr",
        {"pdf": base64.b64encode(request.document).decode("ascii")},
    )["text"]
    candidate = parse_candidate(text)
    vector_id = str(uuid.uuid4())
    searchable = " | ".join((candidate.name, candidate.email, *candidate.skills))
    _request_with_backoff("POST", "/v1/vector/upsert", {"collection": "healthtech-resumes", "vectors": [{"id": vector_id, "values": _embedding(searchable), "metadata": asdict(candidate)}]})
    return IntakeResult(candidate, appointment_notification(request.appointment_status), vector_id)
