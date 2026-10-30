"""Deterministic Anthropic-compatible HTTP fixture for release verification."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re


def answer(body):
    system = body.get("system", "")
    messages = body.get("messages", [])
    first = messages[0].get("content", "") if messages else ""
    if system.startswith("You classify customer support intent"):
        match = re.search(r"Customer message:\n(.+)$", str(first), re.S)
        message = (match.group(1) if match else str(first)).lower()
        if "hello" in message:
            intent = "greeting"
        elif "refund" in message:
            intent = "refund"
        elif "401" in message or "sign-in" in message:
            intent = "technical_login"
        elif "order status" in message:
            intent = "order_status"
        elif "policy" in message:
            intent = "query"
        else:
            intent = "query"
        return [{"type": "text", "text": json.dumps({"intent": intent, "confidence": 0.99, "reasoning": "Deterministic release fixture"})}], "end_turn"
    if system.startswith("Score relevance"):
        return [{"type": "text", "text": '{"relevance":0.9,"accuracy":0.9,"completeness":0.9,"helpfulness":0.9}'}], "end_turn"
    if system.startswith("Return JSON with an array"):
        return [{"type": "text", "text": '{"queries":[]}'}], "end_turn"
    if system.startswith("Return JSON with an ordered array"):
        return [{"type": "text", "text": '{"indices":[0]}'}], "end_turn"
    if system.startswith("Extract only explicitly stated"):
        return [{"type": "text", "text": '{"preferences":[]}'}], "end_turn"
    if "Summarize" in system:
        return [{"type": "text", "text": "The customer asked for support."}], "end_turn"
    try:
        message = json.loads(first).get("message", "")
    except (ValueError, TypeError):
        message = str(first)
    tool_names = {tool.get("name") for tool in body.get("tools", [])}
    has_result = any(isinstance(item.get("content"), list) for item in messages[1:])
    if "policy" in message.lower() and "search_knowledge_base" in tool_names and not has_result:
        return [{"type": "tool_use", "id": "fixture-tool-1", "name": "search_knowledge_base", "input": {"query": message}}], "tool_use"
    return [{"type": "text", "text": "I can help with that request. Please use the approved support process."}], "end_turn"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/messages":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(size))
            content, stop_reason = answer(body)
        except (ValueError, TypeError):
            self.send_error(400)
            return
        payload = json.dumps({"id": "msg_release_fixture", "type": "message", "role": "assistant", "model": body.get("model", "release-test-model"), "content": content, "stop_reason": stop_reason, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 10}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
