"""Create a Foundry Memory Store for long-term memory."""
import os
from dotenv import load_dotenv
load_dotenv()

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions
from azure.identity import DefaultAzureCredential

project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
print(f"Using project endpoint: {project_endpoint}")

project_client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),
)

memory_store_name = "agent_long_term_memory"

options = MemoryStoreDefaultOptions(
    chat_summary_enabled=True,
    user_profile_enabled=True,
    user_profile_details=(
        "Remember user preferences, facts about them (name, role, company), "
        "and topics discussed. Avoid sensitive data like passwords, financial "
        "details, or health information."
    ),
)

definition = MemoryStoreDefaultDefinition(
    chat_model="gpt-4.1",
    embedding_model="text-embedding-3-small",
    options=options,
)

import logging
logging.basicConfig(level=logging.WARNING)

from azure.core.pipeline.policies import RetryPolicy

# First try list to see if it works at all
print("Listing existing memory stores...")
try:
    stores = list(project_client.beta.memory_stores.list())
    print(f"Existing stores: {[s.name for s in stores]}")
except Exception as e:
    print(f"List error: {e}")

print("\nCreating memory store...")
try:
    memory_store = project_client.beta.memory_stores.create(
        name=memory_store_name,
        definition=definition,
        description="Long-term memory store for the LangGraph ReAct agent",
    )
    print(f"Created memory store: {memory_store.name}")
    print(f"Description: {memory_store.description}")
except Exception as e:
    print(f"Error creating: {type(e).__name__}: {e}")
