# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------
import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

from azure.ai.agentserver.langgraph import from_langgraph
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

deployment_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
model = init_chat_model(
    f"azure_openai:{deployment_name}",
    azure_ad_token_provider=get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://learn.microsoft.com/api/mcp")

SYSTEM_PROMPT = (
    "You are a helpful assistant that can search Microsoft Learn documentation. "
    "When the user asks technical questions about Azure, Microsoft products, or development, "
    "use the available tools to search Microsoft Learn and provide accurate answers with sources."
)


async def main():
    """Start the agent server with MCP tools."""
    mcp_client = MultiServerMCPClient(
        {
            "microsoft-learn": {
                "transport": "streamable_http",
                "url": MCP_SERVER_URL,
            }
        }
    )

    tools = await mcp_client.get_tools()
    print(f"Loaded {len(tools)} tools from MCP server:")
    for t in tools:
        print(f"  - {t.name}: {t.description[:80]}...")

    checkpointer = MemorySaver()
    agent = create_react_agent(
        model,
        tools,
        checkpointer=checkpointer,
        prompt=SYSTEM_PROMPT,
    )

    app = from_langgraph(agent)
    await asyncio.to_thread(app.run)


if __name__ == "__main__":
    asyncio.run(main())