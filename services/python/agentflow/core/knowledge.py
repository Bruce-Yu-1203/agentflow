"""Versioned knowledge chunks and provenance-preserving retrieval."""

import asyncio
import hashlib
import json
import re
from typing import Any

import chromadb

from agentflow.core.embedding import local_vector


def chunk_text(content: str, size: int = 500) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", content.strip())
    chunks: list[str] = []
    current = ""
    for part in parts:
        if not part:
            continue
        while len(part) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(part[:size])
            part = part[size:]
        if len(current) + len(part) + 1 > size and current:
            chunks.append(current)
            current = ""
        current = (current + " " + part).strip()
    if current:
        chunks.append(current)
    return chunks


class KnowledgeStore:
    def __init__(self, client: Any | None = None):
        self.client = client or chromadb.EphemeralClient()
        self.collection = self.client.get_or_create_collection("knowledge_base", metadata={"hnsw:space": "cosine"})
        self.version = 0
        self._cache: dict[tuple[str, int, int], list[dict[str, Any]]] = {}

    async def add(self, documents: list[dict[str, str]]) -> dict[str, int]:
        added = 0
        for document in documents:
            title, content = document.get("title", "").strip(), document.get("content", "").strip()
            if not title or not content:
                raise ValueError("Each document needs a title and content")
            doc_id = (document.get("document_id") or title).strip()
            version = hashlib.sha256(content.encode()).hexdigest()
            chunks = chunk_text(content)
            existing = await asyncio.to_thread(self.collection.get, where={"document_id": doc_id})
            ids = existing.get("ids", [])
            if ids:
                await asyncio.to_thread(self.collection.delete, ids=ids)
            chunk_ids = [hashlib.sha256(f"{doc_id}:{index}".encode()).hexdigest() for index in range(len(chunks))]
            metadata = [{"document_id": doc_id, "title": title, "version": version, "chunk": index, "total_chunks": len(chunks)} for index in range(len(chunks))]
            await asyncio.to_thread(self.collection.upsert, ids=chunk_ids, documents=chunks, embeddings=[local_vector(chunk, 384) for chunk in chunks], metadatas=metadata)
            added += len(chunks)
        self.version += 1
        self._cache.clear()
        return {"added_chunks": added, "total_chunks": await self.count()}

    async def count(self) -> int:
        return await asyncio.to_thread(self.collection.count)

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if not query.strip() or len(query) > 2000 or not 1 <= top_k <= 20:
            raise ValueError("Invalid knowledge search query or top_k")
        key = (query, top_k, self.version)
        if key in self._cache:
            return list(self._cache[key])
        if await self.count() == 0:
            return []
        data = await asyncio.to_thread(self.collection.query, query_embeddings=[local_vector(query, 384)], n_results=top_k, include=["documents", "metadatas", "distances"])
        hits = []
        for content, meta, distance in zip(data["documents"][0], data["metadatas"][0], data["distances"][0]):
            hits.append({"title": meta["title"], "content": content, "score": round(1 - distance, 4), "chunk": meta["chunk"], "document_id": meta["document_id"], "version": meta["version"]})
        self._cache[key] = hits
        return list(hits)


def parse_upload(filename: str, content: bytes) -> list[dict[str, str]]:
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("Upload exceeds 10 MB")
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Upload must be UTF-8") from exc
    suffix = filename.rsplit(".", 1)[-1].lower()
    if suffix == "json":
        records = json.loads(decoded)
        if not isinstance(records, list) or not records:
            raise ValueError("JSON upload must be a nonempty document array")
        return [{"title": item["title"], "content": item["content"], **({"document_id": item["document_id"]} if item.get("document_id") else {})} for item in records]
    if suffix in {"txt", "md"}:
        return [{"title": filename, "content": decoded}]
    raise ValueError("Only .txt, .md, and .json uploads are supported")
