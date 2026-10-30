"""Optional query rewriting and reranking around knowledge search."""

import asyncio
import json
from typing import Any

from agentflow.core.knowledge import KnowledgeStore
from agentflow.core.model import ModelClient


class RetrievalPipeline:
    def __init__(self, knowledge: KnowledgeStore, model: ModelClient | None, model_name: str):
        self.knowledge, self.model, self.model_name = knowledge, model, model_name
        self._cache: dict[tuple[str, int, int], dict[str, Any]] = {}

    async def search(self, query: str, top_k: int = 5) -> dict[str, Any]:
        if not query.strip() or len(query) > 2000 or not 1 <= top_k <= 20:
            raise ValueError("Invalid query or top_k")
        key = (query, top_k, self.knowledge.version)
        if key in self._cache:
            return {**self._cache[key], "cached": True}
        queries = [query]
        if self.model:
            try:
                reply = await self.model.complete(stage="query_rewrite", model=self.model_name, system="Return JSON with an array of up to three distinct search queries in English.", messages=[{"role": "user", "content": query}], max_tokens=200, temperature=0.1, timeout=10)
                if not reply.truncated:
                    variants = json.loads(reply.text).get("queries", [])
                    if isinstance(variants, list):
                        queries += [item.strip() for item in variants[:3] if isinstance(item, str) and item.strip() and len(item) <= 2000]
            except Exception:
                pass
        queries = list(dict.fromkeys(queries))
        results = await asyncio.gather(*(self.knowledge.search(item, max(top_k, 5)) for item in queries), return_exceptions=True)
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, int, str]] = set()
        for result in results:
            if isinstance(result, BaseException):
                continue
            for hit in result:
                identity = (hit["document_id"], hit["chunk"], hit["version"])
                if identity not in seen:
                    seen.add(identity)
                    candidates.append(hit)
        reranked = False
        if self.model and len(candidates) > top_k:
            try:
                summaries = [{"index": index, "title": item["title"], "content": item["content"][:350]} for index, item in enumerate(candidates)]
                reply = await self.model.complete(stage="rerank", model=self.model_name, system="Return JSON with an ordered array named indices containing all candidate indices, best evidence first.", messages=[{"role": "user", "content": json.dumps({"query": query, "candidates": summaries})}], max_tokens=300, temperature=0, timeout=30)
                if reply.truncated:
                    raise ValueError("Truncated rerank response")
                indices = json.loads(reply.text)["indices"]
                if not isinstance(indices, list) or len(indices) != len(candidates) or set(indices) != set(range(len(candidates))) or any(type(index) is not int for index in indices):
                    raise ValueError("Invalid rerank indices")
                candidates = [candidates[index] for index in indices]
                reranked = True
            except Exception:
                pass
        output = {"query": query, "results": candidates[:top_k], "reranked": reranked, "cached": False}
        self._cache[key] = output
        return output
