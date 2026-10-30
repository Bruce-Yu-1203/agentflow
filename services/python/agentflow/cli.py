"""Interactive HTTP client for the same chat workflow as the API."""

import argparse
import sys
from typing import Callable, TextIO
from uuid import uuid4

import httpx


def run_chat(api_url: str, token: str = "", *, input_fn: Callable[[str], str] = input, output: TextIO = sys.stdout, send: Callable[[str, dict, dict], dict] | None = None) -> int:
    def http_send(url: str, body: dict, headers: dict) -> dict:
        with httpx.Client(timeout=55) as client:
            response = client.post(url, json=body, headers=headers)
            response.raise_for_status()
            return response.json()

    send = send or http_send
    conv_id: str | None = None
    print("AgentFlow chat. Type /new for a new conversation or /exit to quit.", file=output)
    while True:
        try:
            message = input_fn("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("Goodbye.", file=output)
            return 0
        if message.lower() in {"/exit", "/quit"}:
            print("Goodbye.", file=output)
            return 0
        if message.lower() == "/new":
            conv_id = None
            print("Started a new conversation.", file=output)
            continue
        if not message:
            continue
        body = {"message": message, "client_request_id": str(uuid4())}
        if conv_id:
            body["conv_id"] = conv_id
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            result = send(api_url.rstrip("/") + "/chat", body, headers)
            conv_id = result["conv_id"]
            print(f"AgentFlow: {result['response']}", file=output)
            if result.get("status") != "success":
                print(f"Status: {result.get('status', 'unknown')}", file=output)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            print(f"Request failed: {exc}", file=output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AgentFlow customer-support CLI")
    parser.add_argument("chat", nargs="?", default="chat", choices=["chat"])
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--token", default="")
    args = parser.parse_args(argv)
    return run_chat(args.api_url, args.token)


if __name__ == "__main__":
    raise SystemExit(main())
