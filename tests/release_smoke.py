"""Exercise the isolated Compose verification stack through its HTTP gateway."""

import json
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


BASE = "http://localhost:8082"
ADMIN = "release-admin"
CUSTOMER = "release-customer"


def call(path, method="GET", body=None, token=None, raw=False, content_type=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None and not raw:
        body = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=70) as response:
            data = response.read()
            return response.status, json.loads(data) if response.headers.get("Content-Type", "").startswith("application/json") else data.decode()
    except HTTPError as error:
        return error.code, json.loads(error.read())


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    status, health = call("/api/health")
    require(status == 200 and health["status"] == "ok", "Gateway API health failed")
    status, html = call("/")
    require(status == 200 and 'lang="en"' in html and "AgentFlow Console" in html, "English web entrypoint failed")
    asset = re.search(r'src="([^"]+\.js)"', html)
    require(asset is not None and call(asset.group(1))[0] == 200, "Web asset failed")

    require(call("/api/knowledge/stats")[0] == 401, "Missing token was accepted")
    require(call("/api/knowledge/stats", token=CUSTOMER)[0] == 403, "Customer obtained administrator access")
    require(call("/api/knowledge/stats", token=ADMIN)[0] == 200, "Administrator access failed")
    require(call("/api/metrics", token=CUSTOMER)[0] == 403, "Customer accessed metrics")
    require(call("/api/metrics", token=ADMIN)[0] == 200, "Administrator metrics failed")

    document_id = "release-" + uuid4().hex
    status, added = call("/api/knowledge/add", "POST", {"documents": [{"document_id": document_id, "title": "Return policy", "content": "Return policy requests require an order reference and review by the support team."}]}, ADMIN)
    require(status == 200 and added["added_chunks"] >= 1, "Knowledge import failed")
    status, search = call("/api/search?query=return%20policy", "POST", token=ADMIN)
    require(status == 200 and any(hit["document_id"] == document_id for hit in search["results"]), "Knowledge search failed")
    boundary = "agentflowfixture"
    upload = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"release.txt\"\r\nContent-Type: text/plain\r\n\r\nAn English upload about order references.\r\n--{boundary}--\r\n").encode()
    require(call("/api/knowledge/upload", "POST", upload, ADMIN, raw=True, content_type=f"multipart/form-data; boundary={boundary}")[0] == 200, "Knowledge upload failed")
    require(call("/api/skills", token=ADMIN)[1]["count"] >= 1, "Skills inspection failed")
    require(call("/api/skills/reload", "POST", token=ADMIN)[0] == 200, "Skills reload failed")

    request_id = str(uuid4())
    status, first = call("/api/chat", "POST", {"message": "Hello", "client_request_id": request_id}, CUSTOMER)
    require(status == 200 and first["status"] == "success" and first["conv_id"], "New chat failed")
    status, retry = call("/api/chat", "POST", {"message": "Hello", "client_request_id": request_id}, CUSTOMER)
    require(status == 200 and retry["request_id"] == first["request_id"], "Receipt retry changed the response")
    status, followup = call("/api/chat", "POST", {"message": "What is the order status?", "conv_id": first["conv_id"], "client_request_id": str(uuid4())}, CUSTOMER)
    require(status == 200 and followup["conv_id"] == first["conv_id"], "Follow-up lost its conversation")
    status, mixed = call("/api/chat", "POST", {"message": "Sign-in returns 401 and I was charged twice", "client_request_id": str(uuid4())}, CUSTOMER)
    require(status == 200 and mixed["intent"] == "technical_login" and mixed["primary_agent"] in {"technical", "billing"}, "Mixed-domain routing failed")
    status, policy = call("/api/chat", "POST", {"message": "What is the return policy?", "client_request_id": str(uuid4())}, CUSTOMER)
    require(status == 200 and policy["request_id"], "Policy chat failed")
    status, trace = call("/api/trace/tool/" + policy["request_id"], token=ADMIN)
    require(status == 200 and trace["found"] and trace["trace"]["request_id"] == policy["request_id"], "Tool trace failed")

    cases = {"intent_cases": [{"message": "Hello", "expected_intent": "greeting"}, {"message": "Sign-in returns 401", "expected_intent": "technical_login"}], "dialog_cases": [{"question": "How can I check my order status?", "expected_agent": "general", "reference_answer": "Ask for an order reference."}]}
    status, job = call("/api/eval/run", "POST", cases, ADMIN)
    require(status == 202 and job["job_id"], "Evaluation submission failed")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        status, job = call("/api/eval/jobs/" + job["job_id"], token=ADMIN)
        if job["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.5)
    require(status == 200 and job["status"] == "completed" and job["completed"] == job["total"], "Evaluation did not complete")
    require(job["result"]["intent_count"] == 2, "Evaluation result is incomplete")
    require(call("/api/monitor", token=ADMIN)[0] == 200, "Runtime monitor failed")
    require(call("/api/integrations/mcp", token=ADMIN)[0] == 200, "MCP status failed")
    require(call("/api/integrations/embedding", token=ADMIN)[0] == 200, "Embedding status failed")

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with urlopen("http://localhost:9092/api/v1/targets", timeout=5) as response:
            targets = json.load(response)["data"]["activeTargets"]
        if any(target.get("health") == "up" and target.get("labels", {}).get("job") == "agentflow-api" for target in targets):
            break
        time.sleep(1)
    else:
        raise AssertionError("Prometheus did not scrape the authorized metrics endpoint")
    print("Release smoke passed: gateway, web, storage, auth, chat, retry, routing, knowledge, Skills, traces, evaluation, MCP, monitoring, and Prometheus")


if __name__ == "__main__":
    main()
