"""User-scoped episodic and profile vectors in separate collections."""

import asyncio
import hashlib
import json
from typing import Any

from agentflow.core.embedding import local_vector


class LongTermMemory:
    def __init__(self, chroma_client: Any):
        self.episodes = chroma_client.get_or_create_collection("episodic_memory", metadata={"hnsw:space": "cosine"})
        self.profiles = chroma_client.get_or_create_collection("user_profiles", metadata={"hnsw:space": "cosine"})

    @staticmethod
    def _scope(user_id: str) -> str:
        return hashlib.sha256(user_id.encode()).hexdigest()

    async def add_episode(self, user_id: str, conv_id: str, summary: str) -> None:
        user_scope = self._scope(user_id)
        episode_id = hashlib.sha256(json.dumps([user_scope, conv_id, summary]).encode()).hexdigest()
        await asyncio.to_thread(self.episodes.upsert, ids=[episode_id], documents=[summary[:800]], embeddings=[local_vector(summary, 384)], metadatas=[{"user_scope": user_scope, "conv_id": conv_id}])

    async def relevant(self, user_id: str, conv_id: str, query: str, limit: int = 5) -> list[str]:
        if not query.strip():
            return []
        scope = self._scope(user_id)
        if await asyncio.to_thread(self.episodes.count) == 0:
            return []
        vector = local_vector(query, 384)
        within = await asyncio.to_thread(self.episodes.query, query_embeddings=[vector], n_results=limit, where={"$and": [{"user_scope": scope}, {"conv_id": conv_id}]}, include=["documents"])
        results = list(within["documents"][0])
        if len(results) < limit:
            across = await asyncio.to_thread(self.episodes.query, query_embeddings=[vector], n_results=limit, where={"user_scope": scope}, include=["documents"])
            results = list(dict.fromkeys([*results, *across["documents"][0]]))
        return results[:limit]

    async def update_profile(self, user_id: str, preferences: list[str]) -> None:
        cleaned = [item.strip()[:200] for item in preferences if isinstance(item, str) and item.strip()][:10]
        if not cleaned:
            return
        scope = self._scope(user_id)
        existing = await asyncio.to_thread(self.profiles.get, where={"user_scope": scope})
        if existing["ids"]:
            await asyncio.to_thread(self.profiles.delete, ids=existing["ids"])
        content = "; ".join(cleaned)
        await asyncio.to_thread(self.profiles.upsert, ids=[scope], documents=[content], embeddings=[local_vector(content, 384)], metadatas=[{"user_scope": scope}])

    async def profile(self, user_id: str) -> str:
        existing = await asyncio.to_thread(self.profiles.get, where={"user_scope": self._scope(user_id)}, include=["documents"])
        return existing["documents"][0] if existing["documents"] else ""
