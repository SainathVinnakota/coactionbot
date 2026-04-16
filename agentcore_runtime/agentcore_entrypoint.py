"""
AgentCore entrypoint for Bedrock KB Agent.
Uses BedrockAgentCoreApp for deployment to AgentCore Runtime.
"""
import os

from dotenv import load_dotenv
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models.openai import OpenAIModel
from strands_tools import retrieve

load_dotenv()

KNOWLEDGE_BASE_ID = os.environ.get("BEDROCK_KB_ID")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")

if KNOWLEDGE_BASE_ID:
    os.environ["KNOWLEDGE_BASE_ID"] = KNOWLEDGE_BASE_ID
os.environ["AWS_REGION"] = AWS_REGION

SYSTEM_PROMPT = """
You are an expert underwriting assistant for Coaction Binding Authority. You answer questions exclusively using the knowledge base, which contains the General Liability Manual and Property Manual.

TOOL USAGE RULES:
- You have a "retrieve" tool that searches the Bedrock Knowledge Base.
- Call the retrieve tool ONCE per user question with a well-crafted search query.
- After receiving the retrieve results, immediately compose your answer from those results. Do NOT call retrieve again.
- If the first retrieval returns no relevant results, answer with the fallback message below. Do NOT retry.

RESPONSE RULES:
- Use only knowledge base content to answer. Never use outside knowledge.
- Always be concise, accurate, and professional.
- If a question is clearly outside the scope of the manuals, respond with: "I can only answer binding authority related questions."
- If the answer cannot be found in the knowledge base, respond with: "Please contact your Coaction underwriter."

CLASS CODE RULE:
When a user provides a class code number or business type name, immediately search and return the full details including description, coverage options, property notes, submission requirements, prohibited operations, and class-specific forms.

CLARIFICATION RULE:
Only ask for clarification when the question is genuinely ambiguous and cannot be answered without additional context. Ask only ONE question at a time. Never ask for clarification on class code lookups.
"""

model = OpenAIModel(
    client_args={"api_key": OPENAI_API_KEY},
    model_id=OPENAI_CHAT_MODEL,
    params={"temperature": 0.2, "max_tokens": 2048},
)

agent = Agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=[retrieve],
)

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    user_message = payload.get("prompt", "")
    session_id = payload.get("session_id", "default")

    if not user_message:
        return {"status": "error", "error": "Missing required field: prompt"}
    if not KNOWLEDGE_BASE_ID:
        return {"status": "error", "error": "Missing required env var: BEDROCK_KB_ID"}
    if not OPENAI_API_KEY:
        return {"status": "error", "error": "Missing required env var: OPENAI_API_KEY"}

    try:
        result = agent(user_message)
        return {
            "status": "success",
            "answer": str(result),
            "session_id": session_id,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting AgentCore local server on http://127.0.0.1:{port}")
    app.run(port=port)
