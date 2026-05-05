from __future__ import annotations

import hashlib
import json
from copy import deepcopy
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.io_utils import append_jsonl


DISCLAIMER = (
    "NOTICE: AI-GENERATED ANALYSIS\n"
    "This output supports commercial contract review and negotiation preparation. "
    "It is not legal advice and must be reviewed by qualified counsel."
)


@dataclass
class LLMResponse:
    content: str
    parsed_json: Any | None = None


class LLMClient:
    def __init__(
        self,
        root: Path,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None,
        seed: int,
    ) -> None:
        self.root = root
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.seed = seed
        self.log_path = root / "llm_calls.jsonl"

    def call_json(
        self,
        *,
        stage: str,
        clause_number: str | None,
        prompt_payload: dict[str, Any],
        input_artifacts: list[str],
        output_artifact: str,
        mock_handler,
    ) -> Any:
        prompt_hash = self._prompt_hash(prompt_payload)
        response = self._invoke(prompt_payload, expect_json=True, mock_handler=mock_handler)
        self._log_call(
            stage=stage,
            clause_number=clause_number,
            prompt_hash=prompt_hash,
            input_artifacts=input_artifacts,
            output_artifact=output_artifact,
        )
        return response.parsed_json

    def call_text(
        self,
        *,
        stage: str,
        clause_number: str | None,
        prompt_payload: dict[str, Any],
        input_artifacts: list[str],
        output_artifact: str,
        mock_handler,
    ) -> str:
        prompt_hash = self._prompt_hash(prompt_payload)
        response = self._invoke(prompt_payload, expect_json=False, mock_handler=mock_handler)
        self._log_call(
            stage=stage,
            clause_number=clause_number,
            prompt_hash=prompt_hash,
            input_artifacts=input_artifacts,
            output_artifact=output_artifact,
        )
        return response.content

    def _strip_code_fences(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            inner = lines[1:] if lines[0].strip().startswith("```") else lines
            if inner and inner[-1].strip() == "```":
                inner = inner[:-1]
            return "\n".join(inner).strip()
        return stripped

    def _prompt_hash(self, prompt_payload: dict[str, Any]) -> str:
        serialized = json.dumps(prompt_payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _invoke(self, prompt_payload: dict[str, Any], expect_json: bool, mock_handler) -> LLMResponse:
        if self.provider == "mock":
            mock_output = mock_handler(prompt_payload)
            if expect_json:
                return LLMResponse(content=json.dumps(mock_output), parsed_json=mock_output)
            return LLMResponse(content=str(mock_output))
        if self.provider == "openai" and not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required when provider is not 'mock'.")
        max_attempts = 2 if expect_json else 1
        last_content = ""
        for attempt in range(1, max_attempts + 1):
            attempt_prompt = deepcopy(prompt_payload)
            if expect_json and attempt > 1:
                attempt_prompt["system"] += " Return strictly valid JSON with no markdown fences or commentary."
            payload = self._post_chat_completion(attempt_prompt, expect_json)
            content = self._extract_content(payload)
            last_content = content
            if not expect_json:
                return LLMResponse(content=content)
            try:
                cleaned = self._strip_code_fences(content)
                return LLMResponse(content=content, parsed_json=json.loads(cleaned))
            except json.JSONDecodeError:
                if attempt == max_attempts:
                    raise RuntimeError(f"LLM returned invalid JSON after retry: {content}")
        raise RuntimeError(f"LLM invocation failed without a usable response: {last_content}")

    def _post_chat_completion(self, prompt_payload: dict[str, Any], expect_json: bool) -> dict[str, Any]:
        request_payload = {
            "model": self.model,
            "temperature": 0,
            "seed": self.seed,
            "messages": [
                {
                    "role": "system",
                    "content": prompt_payload["system"],
                },
                {
                    "role": "user",
                    "content": prompt_payload["user"],
                },
            ],
        }
        if expect_json:
            request_payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = json.dumps(request_payload).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM request failed: {exc.code} {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("LLM response missing choices.")
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, list):
            parts = [part.get("text", "") for part in content if isinstance(part, dict)]
            return "".join(parts).strip()
        if isinstance(content, str):
            return content.strip()
        raise RuntimeError("LLM response content format is unsupported.")

    def _log_call(
        self,
        *,
        stage: str,
        clause_number: str | None,
        prompt_hash: str,
        input_artifacts: list[str],
        output_artifact: str,
    ) -> None:
        append_jsonl(
            self.log_path,
            {
                "stage": stage,
                "clause_number": clause_number,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "provider": self.provider,
                "model": self.model,
                "prompt_hash": prompt_hash,
                "input_artifacts": input_artifacts,
                "output_artifact": output_artifact,
            },
        )
