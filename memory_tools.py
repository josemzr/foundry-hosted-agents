"""Foundry Memory integration for LangGraph using langchain-azure-ai.

Uses AzureAIMemoryChatMessageHistory for auto-extraction of memories after
conversations, and AzureAIMemoryRetriever for injecting relevant memories
into agent context.
"""
import os
import logging
import threading

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from langchain_azure_ai.chat_message_histories import AzureAIMemoryChatMessageHistory
from langchain_azure_ai.retrievers import AzureAIMemoryRetriever
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

MEMORY_STORE_NAME = os.getenv("MEMORY_STORE_NAME", "agent_long_term_memory")
MEMORY_SCOPE = os.getenv("MEMORY_SCOPE", "default_user")
PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")

# Thread-local storage for the current user scope.
# Set by call_model() before tool execution so tools know which user to target.
_current_user = threading.local()


def set_current_user(user_id: str):
    """Set the current user scope for memory tools (thread-local)."""
    _current_user.user_id = user_id


def get_current_user() -> str:
    """Get the current user scope. Falls back to MEMORY_SCOPE env var."""
    return getattr(_current_user, 'user_id', MEMORY_SCOPE)


# Patch: langchain-azure-ai 1.1.0 checks for client.memory_stores but
# azure-ai-projects 2.0.0 GA puts it under client.beta.memory_stores.
# This adds memory_stores as a property alias on AIProjectClient.
if not hasattr(AIProjectClient, "memory_stores"):
    AIProjectClient.memory_stores = property(lambda self: self.beta.memory_stores)

_credential = None
_project_client = None


def _get_credential():
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def _get_client() -> AIProjectClient:
    global _project_client
    if _project_client is None:
        from azure.core.pipeline.policies import HTTPPolicy

        class FoundryFeaturesPolicy(HTTPPolicy):
            def send(self, request):
                request.http_request.headers["Foundry-Features"] = "MemoryStores=V1Preview"
                return self.next.send(request)

        _project_client = AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_get_credential(),
            per_call_policies=[FoundryFeaturesPolicy()],
        )
    return _project_client


# Cache session histories
_session_histories: dict[tuple[str, str], AzureAIMemoryChatMessageHistory] = {}


def get_session_history(
    user_id: str,
    session_id: str,
) -> AzureAIMemoryChatMessageHistory:
    """Get or create a memory-backed chat message history for a user/session pair."""
    cache_key = (user_id, session_id)
    if cache_key not in _session_histories:
        _session_histories[cache_key] = AzureAIMemoryChatMessageHistory(
            store_name=MEMORY_STORE_NAME,
            scope=user_id,
            session_id=session_id,
            base_history_factory=lambda _sid: InMemoryChatMessageHistory(),
            project_endpoint=PROJECT_ENDPOINT,
            credential=_get_credential(),
            update_delay=0,
        )
    return _session_histories[cache_key]


def get_memory_retriever(user_id: str, session_id: str) -> AzureAIMemoryRetriever:
    """Get a memory retriever for a user/session pair."""
    return get_session_history(user_id, session_id).get_retriever(k=5)


def get_adhoc_retriever(user_id: str) -> AzureAIMemoryRetriever:
    """Get a standalone retriever for direct memory lookups (no session needed)."""
    return AzureAIMemoryRetriever(
        store_name=MEMORY_STORE_NAME,
        scope=user_id,
        k=5,
        project_endpoint=PROJECT_ENDPOINT,
        credential=_get_credential(),
    )


def retrieve_memories_for_context(user_id: str, session_id: str, query: str) -> str:
    """Retrieve relevant memories and format them for injection into the prompt."""
    try:
        retriever = get_memory_retriever(user_id, session_id)
        docs = retriever.invoke(query)
        if not docs:
            return ""
        return "\n".join(doc.page_content for doc in docs)
    except Exception as e:
        logger.warning(f"Memory retrieval failed: {e}")
        return ""


@tool
def search_memory(query: str) -> str:
    """Search long-term memory for relevant information about the user.
    Use this when you need to recall user preferences, past conversations,
    or previously shared facts."""
    scope = get_current_user()
    try:
        retriever = get_adhoc_retriever(scope)
        docs = retriever.invoke(query)
        if not docs:
            return "No relevant memories found."
        lines = [f"- {doc.page_content}" for doc in docs]
        return "Remembered information:\n" + "\n".join(lines)
    except Exception as e:
        logger.warning(f"Memory search failed: {e}")
        return "Memory search unavailable."


@tool
def save_memory(information: str) -> str:
    """Save important information about the user to long-term memory.
    Use this when the user shares preferences, personal facts, or important
    context that should be remembered across conversations.
    Examples: name, role, company, preferences, dietary restrictions."""
    scope = get_current_user()
    client = _get_client()
    message = {"role": "user", "content": information, "type": "message"}
    try:
        poller = client.beta.memory_stores.begin_update_memories(
            name=MEMORY_STORE_NAME,
            scope=scope,
            items=[message],
            update_delay=0,
        )
        result = poller.result()
        ops = len(result.memory_operations) if result.memory_operations else 0
        return f"Saved to long-term memory for scope '{scope}' ({ops} memory operations)."
    except Exception as e:
        logger.error(f"Memory save failed: {type(e).__name__}: {e}")
        return f"Memory save failed: {e}"
