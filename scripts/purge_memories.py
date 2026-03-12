"""Purge all memories from the Foundry Memory Store."""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from azure.ai.projects import AIProjectClient
from azure.core.pipeline.policies import HTTPPolicy
from azure.identity import DefaultAzureCredential

MEMORY_STORE_NAME = os.getenv("MEMORY_STORE_NAME", "agent_long_term_memory")

class FoundryFeaturesPolicy(HTTPPolicy):
    def send(self, request):
        request.http_request.headers["Foundry-Features"] = "MemoryStores=V1Preview"
        return self.next.send(request)

client = AIProjectClient(
    endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
    per_call_policies=[FoundryFeaturesPolicy()],
)

# Default scopes to purge + any passed as arguments
scopes = ["default_user", "alice", "bob", "f1356774-4df4-4a39-9e8d-6f56fd9090b6"]
if len(sys.argv) > 1:
    scopes = sys.argv[1:]

print(f"Purging memory store: {MEMORY_STORE_NAME}")
for scope in scopes:
    try:
        client.beta.memory_stores.delete_scope(name=MEMORY_STORE_NAME, scope=scope)
        print(f"  Deleted: {scope}")
    except Exception as e:
        print(f"  {scope}: {e}")

print("Done.")
