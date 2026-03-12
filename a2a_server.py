"""A2A Protocol Server — Microsoft Learn Documentation Agent.

Exposes a LangGraph ReAct agent as an A2A-compliant server.
Supports discovery via Agent Card, synchronous and streaming interactions.

Usage:
    uv run python a2a_server.py                    # localhost:10000
    uv run python a2a_server.py --port 8080        # custom port
    uv run python a2a_server.py --host 0.0.0.0     # all interfaces (for ngrok)
"""
import logging
import os

import click
import httpx
import uvicorn
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
)
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from a2a_executor import LearnAgentExecutor

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option("--host", default="localhost", help="Host to bind to")
@click.option("--port", default=10000, help="Port to bind to")
def main(host: str, port: int):
    """Start the Microsoft Learn A2A Agent server."""

    # Use HOST_OVERRIDE for ngrok or external URLs
    public_host = os.getenv("HOST_OVERRIDE", f"http://{host}:{port}")

    capabilities = AgentCapabilities(streaming=True, push_notifications=True)

    skill = AgentSkill(
        id="search_microsoft_learn",
        name="Microsoft Learn Search",
        description="Search Microsoft Learn documentation for information about Azure services, Microsoft products, and development topics",
        tags=["azure", "microsoft", "documentation", "learn", "cloud"],
        examples=[
            "What is Azure Container Apps?",
            "How do I create a Foundry hosted agent?",
            "Explain Azure API Management",
        ],
    )

    agent_card = AgentCard(
        name="Microsoft Learn Agent",
        description="An AI agent that searches Microsoft Learn documentation to answer technical questions about Azure and Microsoft products. Built with LangGraph and Azure OpenAI.",
        url=f"{public_host}/",
        version="1.0.0",
        default_input_modes=["text", "text/plain"],
        default_output_modes=["text", "text/plain"],
        capabilities=capabilities,
        skills=[skill],
    )

    httpx_client = httpx.AsyncClient()
    push_config_store = InMemoryPushNotificationConfigStore()
    push_sender = BasePushNotificationSender(
        httpx_client=httpx_client, config_store=push_config_store
    )

    request_handler = DefaultRequestHandler(
        agent_executor=LearnAgentExecutor(),
        task_store=InMemoryTaskStore(),
        push_config_store=push_config_store,
        push_sender=push_sender,
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    logger.info(f"Starting A2A server on {host}:{port}")
    logger.info(f"Agent Card: {public_host}/.well-known/agent.json")
    logger.info(f"A2A endpoint: {public_host}/")

    uvicorn.run(server.build(), host=host, port=port)


if __name__ == "__main__":
    main()
