"""
Gemini LLM client — direct REST API calls to Google Gemini.

Uses the Gemini REST API directly instead of the SDK to avoid version
compatibility issues. Works on any Python version with `requests`.
"""

from __future__ import annotations

import json
import requests
from typing import Optional

from agent import config

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def call_gemini(
    prompt: str,
    system_instruction: Optional[str] = None,
    temperature: float = 0.0,
) -> str:
    """
    Call the Gemini API and return the text response.

    Args:
        prompt: The user prompt / question.
        system_instruction: Optional system-level instruction.
        temperature: Sampling temperature (0.0 = deterministic).

    Returns:
        The generated text response.

    Raises:
        RuntimeError: If the API call fails.
    """
    url = f"{_API_BASE}/{config.MODEL_NAME}:generateContent?key={config.GOOGLE_API_KEY}"

    # Build the request body
    contents = []

    # System instruction (if provided)
    if system_instruction:
        contents.append({
            "role": "user",
            "parts": [{"text": system_instruction}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": "Understood. I will follow these instructions."}]
        })

    # User prompt
    contents.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })

    body = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 2048,
        },
    }

    # Also try system_instruction field (newer API versions)
    if system_instruction:
        body["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
        # If systemInstruction is supported, we don't need the conversation trick
        # But we keep both for compatibility — the API ignores what it doesn't support
        contents_clean = [{
            "role": "user",
            "parts": [{"text": prompt}]
        }]
        body["contents"] = contents_clean

    try:
        resp = requests.post(url, json=body, timeout=60)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # If systemInstruction isn't supported, fall back to conversation style
        if resp.status_code == 400 and system_instruction:
            body.pop("systemInstruction", None)
            body["contents"] = contents
            resp = requests.post(url, json=body, timeout=60)
            resp.raise_for_status()
        else:
            raise RuntimeError(f"Gemini API error: {resp.status_code} — {resp.text}") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error calling Gemini API: {e}") from e

    data = resp.json()

    # Extract text from response
    try:
        candidates = data["candidates"]
        text = candidates[0]["content"]["parts"][0]["text"]
        return text.strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response format: {data}") from e
