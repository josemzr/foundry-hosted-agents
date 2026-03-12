"""A2A Protocol agent that searches Microsoft Learn documentation.

Uses LangGraph ReAct agent with Azure OpenAI and the Microsoft Learn MCP server
tools, exposed as an A2A-compliant server.
"""
import os
from collections.abc import AsyncIterable
from typing import Any, Literal

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

import httpx

memory = MemorySaver()

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://learn.microsoft.com/api/mcp")


@tool
def search_microsoft_learn(query: str) -> str:
    """Search Microsoft Learn documentation for technical information.

    Args:
        query: The search query about Azure, Microsoft products, or development topics.

    Returns:
        Search results from Microsoft Learn.
    """
    try:
        response = httpx.get(
            "https://learn.microsoft.com/api/search",
            params={"search": query, "locale": "en-us", "$top": 3},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if not results:
            return "No results found."
        output = []
        for r in results[:3]:
            title = r.get("title", "")
            desc = r.get("description", "")
            url = r.get("url", "")
            output.append(f"- **{title}**: {desc}\n  URL: {url}")
        return "\n\n".join(output)
    except Exception as e:
        return f"Search failed: {e}"


class ResponseFormat(BaseModel):
    """Agent response format."""
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


class MicrosoftLearnAgent:
    """Agent that searches Microsoft Learn documentation via A2A protocol."""

    SYSTEM_INSTRUCTION = (
        "You are a Microsoft Learn documentation assistant. "
        "Your purpose is to help users find information about Azure services, "
        "Microsoft products, and development topics using the search_microsoft_learn tool. "
        "Always provide accurate information with source URLs when available. "
        "If the user asks about something unrelated to Microsoft/Azure, "
        "politely redirect them to Microsoft Learn topics."
    )

    FORMAT_INSTRUCTION = (
        "Set response status to input_required if the user needs to provide more information. "
        "Set response status to error if there is an error while processing. "
        "Set response status to completed if the request is complete."
    )

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        deployment_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1")
        self.model = init_chat_model(
            f"azure_openai:{deployment_name}",
            azure_ad_token_provider=get_bearer_token_provider(
                DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            ),
        )
        self.tools = [search_microsoft_learn]
        self.graph = create_react_agent(
            self.model,
            tools=self.tools,
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=(self.FORMAT_INSTRUCTION, ResponseFormat),
        )

    async def stream(self, query: str, context_id: str) -> AsyncIterable[dict[str, Any]]:
        inputs = {"messages": [("user", query)]}
        config = {"configurable": {"thread_id": context_id}}

        for item in self.graph.stream(inputs, config, stream_mode="values"):
            message = item["messages"][-1]
            if isinstance(message, AIMessage) and message.tool_calls:
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": "Searching Microsoft Learn documentation...",
                }
            elif isinstance(message, ToolMessage):
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": "Processing search results...",
                }

        yield self._get_agent_response(config)

    def _get_agent_response(self, config: dict) -> dict[str, Any]:
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get("structured_response")
        if structured_response and isinstance(structured_response, ResponseFormat):
            return {
                "is_task_complete": structured_response.status == "completed",
                "require_user_input": structured_response.status == "input_required",
                "content": structured_response.message,
            }
        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "Unable to process your request. Please try again.",
        }
