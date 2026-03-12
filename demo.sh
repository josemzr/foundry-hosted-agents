#!/bin/bash
# Demo: Foundry Long-Term Memory with LangGraph Agent
# Shows that the agent remembers facts across separate requests

set -e

BASE_URL="http://localhost:8088/responses"

extract_text() {
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('output',d)[-1]['content'][0]['text'] if 'output' in d else d)" 2>/dev/null
}

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Foundry Long-Term Memory Demo                              ║"
echo "║  Agent remembers facts across sessions using Memory Store   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# --- Step 1: Share personal info ---
echo "━━━ Step 1: Share personal information ━━━"
echo ""
echo "USER: Hi! My name is Carlos, I work at Contoso, and I'm allergic to peanuts."
echo ""
RESPONSE=$(curl -s -H "Content-Type: application/json" -X POST "$BASE_URL" \
  -d '{"input":"Hi! My name is Carlos, I work at Contoso, and I am allergic to peanuts. I prefer tea over coffee.","stream":false}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

read -p "Press Enter to continue..."
echo ""

# --- Step 2: Ask what it remembers ---
echo "━━━ Step 2: Ask the agent what it remembers ━━━"
echo ""
echo "USER: What do you remember about me?"
echo ""
RESPONSE=$(curl -s -H "Content-Type: application/json" -X POST "$BASE_URL" \
  -d '{"input":"What do you remember about me?","stream":false}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

read -p "Press Enter to continue..."
echo ""

# --- Step 3: Add more preferences ---
echo "━━━ Step 3: Share more preferences ━━━"
echo ""
echo "USER: I also love hiking and I'm learning Japanese."
echo ""
RESPONSE=$(curl -s -H "Content-Type: application/json" -X POST "$BASE_URL" \
  -d '{"input":"I also love hiking and I am learning Japanese.","stream":false}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

read -p "Press Enter to continue..."
echo ""

# --- Step 4: Cross-session recall ---
echo "━━━ Step 4: Simulating a NEW session — can it still recall? ━━━"
echo ""
echo "USER: Can you suggest a snack for me? Remember my allergies!"
echo ""
RESPONSE=$(curl -s -H "Content-Type: application/json" -X POST "$BASE_URL" \
  -d '{"input":"Can you suggest a snack for me? Remember my allergies!","stream":false}')
echo "AGENT: $(echo "$RESPONSE" | extract_text)"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Demo complete! The agent used Foundry Memory Store to:"
echo "  • Save user facts (name, company, allergies, preferences)"
echo "  • Retrieve relevant memories before each response"
echo "  • Apply stored knowledge (allergy) to recommendations"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
