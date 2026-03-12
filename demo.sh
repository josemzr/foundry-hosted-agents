#!/usr/bin/env bash
# =============================================================================
# demo.sh — Persistent Short-Term Memory with Cosmos DB
#
# This script demonstrates how the agent remembers context across requests
# using Azure Cosmos DB as a checkpointer, and how different conversation
# threads maintain separate memory.
#
# Prerequisites:
#   - Agent running locally: uv run main.py
#   - .env configured with COSMOSDB_ENDPOINT and COSMOSDB_KEY
# =============================================================================

set -euo pipefail

BASE_URL="http://localhost:8088/responses"
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

send_message() {
    local thread="$1"
    local message="$2"
    local label="$3"

    echo -e "${BLUE}[$thread]${NC} ${YELLOW}→ $message${NC}"

    local body
    if [ "$thread" = "no-thread" ]; then
        body="{\"input\":\"$message\",\"stream\":false}"
    else
        body="{\"input\":\"$message\",\"stream\":false,\"conversation\":{\"id\":\"$thread\"}}"
    fi

    local response
    response=$(curl -s "$BASE_URL" \
        -H "Content-Type: application/json" \
        -d "$body" 2>&1)

    local text
    text=$(echo "$response" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['output'][-1]['content'][0]['text'])" 2>/dev/null || echo "ERROR: $response")

    echo -e "${BLUE}[$thread]${NC} ${GREEN}← $text${NC}"
    echo ""
}

echo "=============================================="
echo "  Persistent Short-Term Memory Demo"
echo "  Backed by Azure Cosmos DB"
echo "=============================================="
echo ""

# ─────────────────────────────────────────────────
# Part 1: Memory within a conversation thread
# ─────────────────────────────────────────────────
echo -e "${YELLOW}━━━ Part 1: Memory within a thread ━━━${NC}"
echo "The agent remembers information within the same conversation thread."
echo ""

send_message "customer-alice" "Hi! My name is Alice and I work at Contoso." "Introduce"
send_message "customer-alice" "What company do I work at?" "Recall company"

echo -e "${GREEN}✓ The agent remembered Alice's company from the same thread.${NC}"
echo ""

# ─────────────────────────────────────────────────
# Part 2: Thread isolation
# ─────────────────────────────────────────────────
echo -e "${YELLOW}━━━ Part 2: Thread isolation ━━━${NC}"
echo "Different threads have separate memory — the agent does NOT know Alice here."
echo ""

send_message "customer-bob" "Hi! I'm Bob. What do you know about Alice?" "Cross-thread test"

echo -e "${GREEN}✓ Bob's thread has no knowledge of Alice — threads are isolated.${NC}"
echo ""

# ─────────────────────────────────────────────────
# Part 3: Persistence across restarts
# ─────────────────────────────────────────────────
echo -e "${YELLOW}━━━ Part 3: Persistence ━━━${NC}"
echo "Because checkpoints are stored in Cosmos DB, memory survives server restarts."
echo "Try restarting the server (Ctrl+C, then uv run main.py) and run:"
echo ""
echo -e "  ${BLUE}curl -s $BASE_URL \\\\${NC}"
echo -e "  ${BLUE}  -H 'Content-Type: application/json' \\\\${NC}"
echo -e "  ${BLUE}  -d '{\"input\":\"What is my name?\",\"stream\":false,\"conversation\":{\"id\":\"customer-alice\"}}'${NC}"
echo ""
echo "The agent should still remember Alice!"
echo ""

# ─────────────────────────────────────────────────
# Part 4: Inspect data in Cosmos DB
# ─────────────────────────────────────────────────
echo -e "${YELLOW}━━━ Part 4: Cosmos DB inspection ━━━${NC}"
echo "Checking checkpoints stored in Cosmos DB..."
echo ""

python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()

from langgraph_checkpoint_cosmosdb import CosmosDBSaver

saver = CosmosDBSaver('agent-memory', 'checkpoints')
items = list(saver.container.read_all_items())

# Group by thread
threads = {}
for item in items:
    item_id = item['id']
    parts = item_id.split('\$')
    if len(parts) >= 3:
        thread = parts[1]
        threads.setdefault(thread, []).append(item_id)

print(f'Total items in Cosmos DB: {len(items)}')
print(f'Threads found: {len(threads)}')
print()
for thread, keys in sorted(threads.items()):
    checkpoints = [k for k in keys if k.startswith('checkpoint')]
    writes = [k for k in keys if k.startswith('writes')]
    print(f'  Thread: {thread[:50]}...')
    print(f'    Checkpoints: {len(checkpoints)}, Writes: {len(writes)}')
print()
" 2>/dev/null || echo "(Install dotenv and run from project directory)"

echo "=============================================="
echo "  Demo complete!"
echo "=============================================="
echo ""
echo "Key takeaways:"
echo "  • Use 'conversation.id' in the request body to set the thread ID"
echo "  • Same thread → agent remembers context"
echo "  • Different thread → separate memory"
echo "  • Cosmos DB persists checkpoints across server restarts"
echo "  • Checkpoints are stored in DB: agent-memory, container: checkpoints"
