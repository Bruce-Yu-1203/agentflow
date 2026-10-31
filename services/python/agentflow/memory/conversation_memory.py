"""Redis conversation records, receipts, and lease-protected commits."""

import asyncio
from dataclasses import dataclass
import hashlib
import json
from uuid import uuid4
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import WatchError


class ReceiptConflict(Exception):
    pass


class LeaseLost(Exception):
    pass


def _scope(user_id: str, conv_id: str) -> str:
    return hashlib.sha256(json.dumps([user_id, conv_id], separators=(",", ":")).encode()).hexdigest()


@dataclass
class ConversationContext:
    history: list[dict[str, str]]
    state: dict[str, Any]
    summary: str = ""


class ConversationStore:
    def __init__(self, redis: Redis, *, ttl: int = 86400, lease_seconds: int = 120):
        self.redis = redis
        self.ttl = ttl
        self.lease_seconds = lease_seconds
        self._local: dict[str, asyncio.Lock] = {}

    def keys(self, user_id: str, conv_id: str, client_request_id: str) -> tuple[str, str, str, str]:
        prefix = "agentflow:conv:" + _scope(user_id, conv_id)
        receipt = prefix + ":receipt:" + hashlib.sha256(client_request_id.encode()).hexdigest()
        return prefix + ":lock", prefix + ":context", receipt, prefix + ":trace"

    async def acquire(self, user_id: str, conv_id: str, client_request_id: str) -> "ConversationLease":
        lock_key = self.keys(user_id, conv_id, client_request_id)[0]
        local = self._local.setdefault(lock_key, asyncio.Lock())
        await asyncio.wait_for(local.acquire(), timeout=30)
        token = str(uuid4())
        try:
            for _ in range(60):
                if await self.redis.set(lock_key, token, ex=self.lease_seconds, nx=True):
                    return ConversationLease(self, lock_key, token, local)
                await asyncio.sleep(0.5)
            raise TimeoutError("Conversation lock acquisition timed out")
        except BaseException:
            local.release()
            raise

    async def context(self, user_id: str, conv_id: str, client_request_id: str) -> ConversationContext:
        raw = await self.redis.get(self.keys(user_id, conv_id, client_request_id)[1])
        if not raw:
            return ConversationContext([], {})
        data = json.loads(raw)
        return ConversationContext(data.get("history", []), data.get("state", {}), data.get("summary", ""))

    async def receipt(self, user_id: str, conv_id: str, client_request_id: str, message: str) -> dict[str, Any] | None:
        raw = await self.redis.get(self.keys(user_id, conv_id, client_request_id)[2])
        if not raw:
            return None
        receipt = json.loads(raw)
        if receipt["message_hash"] != hashlib.sha256(message.encode()).hexdigest():
            raise ReceiptConflict("The client request ID was already used for a different message")
        return receipt

    async def commit(self, lease: "ConversationLease", user_id: str, conv_id: str, client_request_id: str, message: str, response: dict[str, Any], context: ConversationContext, state: dict[str, Any], trace: list[dict[str, Any]]) -> None:
        if lease.lost:
            raise LeaseLost("Conversation lease was lost")
        lock_key, context_key, receipt_key, trace_key = self.keys(user_id, conv_id, client_request_id)
        history = list(context.history)
        if response["status"] != "failed":
            history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": response["response"]}])
            history = history[-20:]
        record = {"history": history, "state": state if response["status"] != "failed" else context.state, "summary": context.summary}
        receipt = {"message_hash": hashlib.sha256(message.encode()).hexdigest(), "response": response, "retryable": response.get("retryable", False)}
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.watch(lock_key)
            if await pipe.get(lock_key) != lease.token:
                lease.lost = True
                raise LeaseLost("Conversation lease was lost before commit")
            pipe.multi()
            pipe.set(context_key, json.dumps(record), ex=self.ttl)
            pipe.set(receipt_key, json.dumps(receipt), ex=self.ttl)
            if trace:
                pipe.set(trace_key, json.dumps(trace), ex=self.ttl)
            try:
                await pipe.execute()
            except WatchError as exc:
                lease.lost = True
                raise LeaseLost("Conversation lease changed before commit") from exc
        if lease.lost:
            lease.lost = True
            raise LeaseLost("Conversation lease was lost before commit")

    async def compress(self, user_id: str, conv_id: str, client_request_id: str, model: Any, model_name: str) -> str | bool:
        context_key = self.keys(user_id, conv_id, client_request_id)[1]
        raw = await self.redis.get(context_key)
        if not raw:
            return False
        snapshot = json.loads(raw)
        history = snapshot.get("history", [])
        if len(history) < 15:
            return False
        try:
            reply = await model.complete(
                stage="summary", model=model_name,
                system="Summarize the customer's issue and confirmed facts in English. Do not invent facts.",
                messages=[{"role": "user", "content": json.dumps({"previous_summary": snapshot.get("summary", ""), "messages": history[:-5]})}],
                max_tokens=400, temperature=0.1, timeout=15,
            )
            if reply.truncated or not reply.text.strip():
                return False
            summary = reply.text.strip()[:800]
            async with self.redis.pipeline(transaction=True) as pipe:
                await pipe.watch(context_key)
                if await pipe.get(context_key) != raw:
                    return False
                snapshot["history"] = history[-5:]
                snapshot["summary"] = summary
                pipe.multi()
                pipe.set(context_key, json.dumps(snapshot), ex=self.ttl)
                await pipe.execute()
            return summary
        except Exception:
            return False


class ConversationLease:
    def __init__(self, store: ConversationStore, key: str, token: str, local: asyncio.Lock):
        self.store, self.key, self.token, self.local = store, key, token, local
        self.lost = False
        self._renew_task: asyncio.Task | None = None

    async def __aenter__(self) -> "ConversationLease":
        self._renew_task = asyncio.create_task(self._renew())
        return self

    async def _renew(self) -> None:
        try:
            while True:
                await asyncio.sleep(max(1, self.store.lease_seconds // 3))
                if not await self._update_lease(renew=True):
                    self.lost = True
                    return
        except asyncio.CancelledError:
            return

    async def __aexit__(self, *_: object) -> None:
        if self._renew_task:
            self._renew_task.cancel()
            await asyncio.gather(self._renew_task, return_exceptions=True)
        await self._update_lease(renew=False)
        self.local.release()

    async def _update_lease(self, *, renew: bool) -> bool:
        try:
            async with self.store.redis.pipeline(transaction=True) as pipe:
                await pipe.watch(self.key)
                if await pipe.get(self.key) != self.token:
                    return False
                pipe.multi()
                if renew:
                    pipe.expire(self.key, self.store.lease_seconds)
                else:
                    pipe.delete(self.key)
                await pipe.execute()
                return True
        except WatchError:
            return False
