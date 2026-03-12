# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------
import os

from dotenv import load_dotenv
load_dotenv()

from azure.ai.agentserver.langgraph import from_langgraph
from azure.ai.agentserver.langgraph.tools import use_foundry_tools
# from azure.ai.agentserver.langgraph.checkpointer import FoundryCheckpointSaver
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
# from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver
from patches.cosmosdbSaver import CosmosDBSaver

deployment_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
model = init_chat_model(
    f"azure_openai:{deployment_name}",
    azure_ad_token_provider=get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
)

foundry_tools = []
if project_tool_connection_id := os.environ.get("AZURE_AI_PROJECT_TOOL_CONNECTION_ID"):
    foundry_tools.append({"type": "mcp", "project_connection_id": project_tool_connection_id})

# Checkpointer: use Cosmos DB for persistent short-term memory, fallback to MemorySaver
# CosmosDBSaver reads from env vars: COSMOSDB_ENDPOINT and COSMOSDB_KEY
if os.environ.get("COSMOSDB_ENDPOINT"):
    checkpointer = CosmosDBSaver(
        database_name="agent-memory",
        container_name="checkpoints",
    )
else:
    checkpointer = MemorySaver()

agent = create_agent(model, checkpointer=checkpointer, middleware=[use_foundry_tools(foundry_tools)])

if __name__ == "__main__":
    from_langgraph(agent).run()