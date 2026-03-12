# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------
import os
import json
import uuid

from dotenv import load_dotenv
load_dotenv()

from azure.ai.agentserver.langgraph import from_langgraph
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
import httpx

deployment_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1")
api_version = os.getenv("OPENAI_API_VERSION", "2025-03-01-preview")

# Derive Azure OpenAI endpoint from project endpoint if not explicitly set
azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
if not azure_endpoint:
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
    # Extract account name: https://<account>.services.ai.azure.com/api/projects/<project>
    if ".services.ai.azure.com" in project_endpoint:
        account = project_endpoint.split("//")[1].split(".")[0]
        azure_endpoint = f"https://{account}.openai.azure.com/"

model_kwargs = {
    "api_version": api_version,
    "azure_ad_token_provider": get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    ),
}
if azure_endpoint:
    model_kwargs["azure_endpoint"] = azure_endpoint

model = init_chat_model(f"azure_openai:{deployment_name}", **model_kwargs)

A2A_AGENT_URL = os.getenv("A2A_AGENT_URL", "https://hosted-agents-apim2.azure-api.net/microsoft-learn-a2a/")


@tool
def ask_microsoft_learn_agent(query: str) -> str:
    """Ask the Microsoft Learn documentation agent a question via A2A protocol.
    Use this tool when the user asks about Azure services, Microsoft products,
    or any technical documentation topic."""
    payload = {
        "id": str(uuid.uuid4()),
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": uuid.uuid4().hex,
                "role": "user",
                "parts": [{"kind": "text", "text": query}],
            }
        },
    }
    try:
        response = httpx.post(
            A2A_AGENT_URL,
            json=payload,
            timeout=120,
            headers={"ngrok-skip-browser-warning": "true"},
        )
        data = response.json()
        result = data.get("result", {})

        # Extract from artifacts
        for artifact in result.get("artifacts", []):
            for part in artifact.get("parts", []):
                if part.get("kind") == "text":
                    return part["text"]

        # Extract from status message
        status = result.get("status", {})
        msg = status.get("message", {})
        if isinstance(msg, dict):
            for part in msg.get("parts", []):
                if part.get("kind") == "text":
                    return part["text"]

        return f"A2A agent responded but no text found: {json.dumps(result)[:500]}"
    except Exception as e:
        return f"Error calling A2A agent: {e}"


checkpointer = MemorySaver()

SYSTEM_PROMPT = (
    "You are a helpful assistant with access to an external Microsoft Learn documentation agent. "
    "When the user asks technical questions about Azure, Microsoft products, or development topics, "
    "use the ask_microsoft_learn_agent tool to get accurate answers from Microsoft Learn. "
    "Always provide clear, concise responses based on the tool results."
)

agent = create_agent(
    model,
    tools=[ask_microsoft_learn_agent],
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
)

if __name__ == "__main__":
    from_langgraph(agent).run()