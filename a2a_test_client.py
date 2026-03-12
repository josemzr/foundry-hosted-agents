"""A2A Test Client — Sends messages to an A2A-compliant agent.

Usage:
    uv run python a2a_test_client.py                           # localhost:10000
    uv run python a2a_test_client.py --url https://abc.ngrok.io  # ngrok URL
"""
import asyncio
import json
import uuid

import click
import httpx


async def send_message(url: str, message: str, context_id: str | None = None):
    """Send a message to an A2A agent and print the response."""
    payload = {
        "id": str(uuid.uuid4()),
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": uuid.uuid4().hex,
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
            }
        },
    }

    if context_id:
        payload["params"]["message"]["contextId"] = context_id

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, json=payload)
        data = response.json()

        # Extract the result
        result = data.get("result", data)

        # Print context_id for multi-turn
        ctx = result.get("contextId", "")

        # Print status
        status = result.get("status", {})
        state = status.get("state", "unknown")

        # Print agent messages from history
        history = result.get("history", [])
        for msg in history:
            if msg.get("role") == "agent":
                for part in msg.get("parts", []):
                    if part.get("kind") == "text":
                        print(f"  AGENT: {part['text']}")

        # Print artifacts
        artifacts = result.get("artifacts", [])
        for artifact in artifacts:
            for part in artifact.get("parts", []):
                if part.get("kind") == "text":
                    print(f"  RESULT: {part['text']}")

        print(f"  [state={state}, contextId={ctx[:20]}...]")
        return ctx


@click.command()
@click.option("--url", default="http://localhost:10000", help="A2A agent URL")
def main(url: str):
    """Interactive A2A test client."""
    print(f"Connecting to A2A agent at {url}")
    print(f"Fetching Agent Card from {url}/.well-known/agent.json ...")

    # Fetch agent card
    resp = httpx.get(f"{url}/.well-known/agent.json")
    if resp.status_code == 200:
        card = resp.json()
        print(f"  Name: {card.get('name')}")
        print(f"  Description: {card.get('description')}")
        skills = card.get("skills", [])
        for s in skills:
            print(f"  Skill: {s.get('name')} — {s.get('description', '')[:80]}")
    else:
        print(f"  Warning: Could not fetch agent card ({resp.status_code})")

    print()
    print("Type your messages (Ctrl+C to exit):")
    print()

    context_id = None
    while True:
        try:
            user_input = input("YOU: ")
            if not user_input.strip():
                continue
            print()
            context_id = asyncio.run(send_message(url, user_input, context_id))
            print()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()
