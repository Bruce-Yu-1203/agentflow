"""Intent-template embedding with whole-space local fallback."""

import asyncio
import hashlib
import json
import math
import time
from typing import Any

import httpx


def local_vector(text: str, dimensions: int = 256) -> list[float]:
    normalized = text.lower().strip()
    grams = {normalized[index:index + size] for size in (1, 2, 3) for index in range(max(0, len(normalized) - size + 1))}
    if not grams:
        return [0.0] * dimensions
    vector = [0.0] * dimensions
    for gram in grams:
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        position = int.from_bytes(digest[:4], "big") % dimensions
        vector[position] += 1.0 if digest[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions differ")
    return sum(a * b for a, b in zip(left, right))


class IntentEmbedding:
    def __init__(
        self,
        *,
        provider: str = "auto",
        api_key: str = "",
        endpoint: str = "https://api.siliconflow.cn/v1/embeddings",
        model: str = "BAAI/bge-m3",
    ):
        if provider not in {"auto", "local", "online"}:
            raise ValueError("Embedding provider must be auto, local, or online")
        self.provider = provider
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self._remote_templates: dict[str, dict[str, list[list[float]]]] = {}
        self._local_templates: dict[str, dict[str, list[list[float]]]] = {}
        self._lock = asyncio.Lock()
        self.retry_at = 0.0
        self.last_error: str | None = None
        self.last_source = "local-ngram"
        self.last_dimensions = 256

    @property
    def online_configured(self) -> bool:
        return self.provider != "local" and bool(self.api_key)

    def status(self) -> dict[str, Any]:
        return {
            "configured_provider": self.provider,
            "online_configured": self.online_configured,
            "model": self.model if self.online_configured else "local-ngram-256",
            "last_source": self.last_source,
            "last_error": self.last_error,
            "last_dimensions": self.last_dimensions,
            "retry_after_s": round(max(0.0, self.retry_at - time.monotonic()), 1),
        }

    async def vectors(self, text: str, templates: dict[str, list[str]]) -> tuple[dict[str, list[list[float]]], list[float], str]:
        snapshot = {name: tuple(values) for name, values in templates.items()}
        fingerprint = hashlib.sha256(json.dumps([self.model, snapshot], sort_keys=True).encode()).hexdigest()
        if self.online_configured and time.monotonic() >= self.retry_at:
            try:
                async with asyncio.timeout(8):
                    async with httpx.AsyncClient(timeout=6, follow_redirects=False) as client:
                        async with self._lock:
                            if fingerprint not in self._remote_templates:
                                flat = [item for values in snapshot.values() for item in values]
                                embedded: list[list[float]] = []
                                for offset in range(0, len(flat), 32):
                                    embedded.extend(await self._request(client, flat[offset:offset + 32]))
                                groups: dict[str, list[list[float]]] = {}
                                offset = 0
                                for name, values in snapshot.items():
                                    groups[name] = embedded[offset:offset + len(values)]
                                    offset += len(values)
                                self._remote_templates = {fingerprint: groups}
                        groups = self._remote_templates[fingerprint]
                        query = (await self._request(client, [text]))[0]
                        if any(len(vector) != len(query) for values in groups.values() for vector in values):
                            self._remote_templates.clear()
                            raise ValueError("Query and template dimensions differ")
                        self.last_source = f"online/{self.model}"
                        self.last_dimensions = len(query)
                        self.last_error = None
                        return groups, query, self.last_source
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"http_{exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
                self.retry_at = time.monotonic() + 60
        if fingerprint not in self._local_templates:
            self._local_templates = {fingerprint: {name: [local_vector(item) for item in values] for name, values in snapshot.items()}}
        query = local_vector(text)
        self.last_source = "local-ngram"
        self.last_dimensions = len(query)
        return self._local_templates[fingerprint], query, self.last_source

    async def _request(self, client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
        response = await client.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts, "encoding_format": "float"},
        )
        response.raise_for_status()
        rows = response.json().get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise ValueError("Invalid embedding response count")
        result: list[list[float] | None] = [None] * len(texts)
        dimension = None
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Invalid embedding row")
            index, vector = row.get("index"), row.get("embedding")
            if type(index) is not int or not 0 <= index < len(texts) or result[index] is not None:
                raise ValueError("Invalid embedding index")
            if not isinstance(vector, list) or not vector or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
                raise ValueError("Invalid embedding vector")
            norm = math.sqrt(sum(value * value for value in vector))
            if not math.isfinite(norm) or norm == 0 or (dimension is not None and len(vector) != dimension):
                raise ValueError("Invalid embedding norm or dimensions")
            dimension = len(vector)
            result[index] = [value / norm for value in vector]
        if any(value is None for value in result):
            raise ValueError("Missing embedding row")
        return [value for value in result if value is not None]
