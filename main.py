# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------
import os
import re

from dotenv import load_dotenv
load_dotenv()

from azure.ai.agentserver.langgraph import from_langgraph
from azure.ai.agentserver.langgraph.tools import use_foundry_tools
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.prebuilt import ToolNode

from memory_tools import (
    search_memory,
    save_memory,
    retrieve_memories_for_context,
    set_current_user,
    MEMORY_SCOPE,
)

deployment_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
model = init_chat_model(
    f"azure_openai:{deployment_name}",
    azure_ad_token_provider=get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
)

# Memory tools available to the agent
memory_tools_list = [search_memory, save_memory]
model_with_tools = model.bind_tools(memory_tools_list)

SYSTEM_PROMPT = (
    "You are a helpful assistant with long-term memory powered by Foundry Memory Store. "
    "IMPORTANT RULES:\n"
    "1. When the user shares ANY personal information (name, preferences, workplace, etc.), "
    "you MUST call the save_memory tool to store it BEFORE responding.\n"
    "2. When the user asks about previously shared information or what you remember, "
    "you MUST call the search_memory tool BEFORE responding.\n"
    "3. Always acknowledge when you've saved or retrieved memories.\n"
    "4. You have two memory tools available: save_memory and search_memory. Use them proactively."
)


def extract_user_id(message) -> tuple[str, str]:
    """Extract [user_id:xxx] prefix from message if present.
    Returns (user_id, clean_message). APIM injects this prefix from JWT OID."""
    # Handle content that may be a list of content blocks (Responses API format)
    if isinstance(message, list):
        message = " ".join(
            block.get("text", str(block)) if isinstance(block, dict) else str(block)
            for block in message
        )
    if not isinstance(message, str):
        return MEMORY_SCOPE, str(message)
    match = re.match(r'^\[user_id:([^\]]+)\]\s*', message)
    if match:
        return match.group(1), message[match.end():]
    return MEMORY_SCOPE, message


def call_model(state: MessagesState, config: RunnableConfig):
    """Call the model with memory context injected."""
    query = state["messages"][-1].content if state["messages"] else ""

    # Extract user_id from input prefix (injected by APIM or manually)
    user_id, clean_query = extract_user_id(query)
    session_id = config.get("configurable", {}).get("thread_id", "default")

    # Set the current user for memory tools (thread-local)
    set_current_user(user_id)

    # Retrieve relevant memories for this user
    memory_text = retrieve_memories_for_context(user_id, session_id, clean_query)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if memory_text:
        messages.append({"role": "system", "content": f"Relevant memories:\n{memory_text}"})

    # Replace the last message with the clean version (without prefix)
    clean_messages = list(state["messages"])
    if clean_messages and clean_query != query:
        clean_messages[-1] = HumanMessage(content=clean_query)
    messages.extend(clean_messages)

    response = model_with_tools.invoke(messages)
    return {"messages": [response]}


def should_continue(state: MessagesState):
    """Check if the agent should continue (tool calls) or end."""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


# Build the graph
tool_node = ToolNode(memory_tools_list)
graph = StateGraph(MessagesState)
graph.add_node("agent", call_model)
graph.add_node("tools", tool_node)
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")

checkpointer = MemorySaver()
agent = graph.compile(checkpointer=checkpointer)

# foundry_tools = []
# if project_tool_connection_id := os.environ.get("AZURE_AI_PROJECT_TOOL_CONNECTION_ID"):
#     foundry_tools.append({"type": "mcp", "project_connection_id": project_tool_connection_id})

if __name__ == "__main__":
    app = from_langgraph(agent)
    # if foundry_tools:
    #     app = from_langgraph(agent, middleware=[use_foundry_tools(foundry_tools)])
    app.run()