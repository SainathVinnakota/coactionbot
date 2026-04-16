"""
Conversational RAG Agent using AWS Bedrock Knowledge Base.
Uses OpenAI GPT-4o for reasoning and Bedrock KB for retrieval.
"""
import asyncio
import os
from strands import Agent
from strands.models.openai import OpenAIModel
from strands_tools import retrieve
from app.config import get_settings
from app.session_manager import SessionManager
from app.logger import get_logger

logger = get_logger(__name__)

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


class BedrockKBAgent:
    """Strands Agent with OpenAI LLM and Bedrock Knowledge Base retrieval."""

    def __init__(self, session_manager: SessionManager, knowledge_base_id: str | None = None):
        self.session_manager = session_manager
        self.agents: dict[str, Agent] = {}
        self.settings = get_settings()
        self.knowledge_base_id = knowledge_base_id or self.settings.bedrock_kb_id
        if not self.knowledge_base_id:
            raise ValueError("BEDROCK_KB_ID is required")
        if not self.settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")
        logger.info("bedrock_kb_agent_initialized", kb_id=self.knowledge_base_id)

    def _get_or_create_agent(self, session_id: str) -> Agent:
        if session_id not in self.agents:
            logger.info("creating_agent_for_session", session_id=session_id)
            
            # Set environment variables for the retrieve tool (still uses Bedrock KB via boto3)
            os.environ["KNOWLEDGE_BASE_ID"] = self.knowledge_base_id
            os.environ["AWS_REGION"] = self.settings.aws_region
            if self.settings.aws_access_key_id:
                os.environ["AWS_ACCESS_KEY_ID"] = self.settings.aws_access_key_id
            if self.settings.aws_secret_access_key:
                os.environ["AWS_SECRET_ACCESS_KEY"] = self.settings.aws_secret_access_key
            
            # Initialize OpenAI model (GPT-4o)
            model = OpenAIModel(
                client_args={
                    "api_key": self.settings.openai_api_key,
                },
                model_id=self.settings.openai_chat_model,
                params={
                    "temperature": 0.2,
                    "max_tokens": 2048
                }
            )
            
            # Create agent with KB retrieve tool
            self.agents[session_id] = Agent(
                model=model,
                system_prompt=SYSTEM_PROMPT,
                tools=[retrieve],
            )
        
        return self.agents[session_id]

    async def query(
        self,
        session_id: str,
        query: str,
        top_k: int = 5
    ) -> tuple[str, list[str], list[str]]:
        """Process a query within a conversation session."""
        logger.info("processing_query", session_id=session_id)

        agent = self._get_or_create_agent(session_id)
        self.session_manager.add_message(session_id, "user", query)

        # Run agent
        response = await asyncio.to_thread(lambda: agent(query))
        answer = str(response)

        self.session_manager.add_message(session_id, "assistant", answer)
        logger.info("query_processed", session_id=session_id)

        # Extract sources and generate follow-up questions
        sources, follow_up_questions = await asyncio.gather(
            self._extract_sources_from_response(answer),
            self._generate_follow_up_questions(query, answer),
        )

        return answer, sources, follow_up_questions

    # Phrases that indicate the answer was NOT grounded in retrieved content
    _FALLBACK_PHRASES = (
        "not available in the binding authority",
        "please contact your underwriter",
        "i can only assist with",
        "no relevant context found",
    )

    async def _extract_sources_from_response(self, answer: str) -> list[str]:
        """Extract source URLs from agent response."""
        # Don't show sources for fallback / out-of-scope answers
        answer_lower = answer.lower()
        if any(phrase in answer_lower for phrase in self._FALLBACK_PHRASES):
            return []
        
        # Bedrock KB includes citations in response
        # Extract URLs from citations if present
        import re
        urls = re.findall(r'https?://[^\s<>"]+', answer)
        return list(dict.fromkeys(urls))[:3]  # Dedupe and limit to 3

    async def _generate_follow_up_questions(self, query: str, answer: str) -> list[str]:
        """Generate follow-up questions using Bedrock."""
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            
            prompt = (
                f"Based on the following conversation context with an AI agent, generate clarification questions (if required) and exactly 3 relevant "
                f"follow-up questions that the user might want to ask next.\n\n"
                f"User's Previous Question: {query}\n\n"
                f"Agent's Response: {answer}\n\n"
                f"Requirements:\n"
                f"- First, generate 1–2 clarification questions ONLY if additional information is required to answer accurately\n"
                f"- Clarification questions should be asked when:\n"
                f"  • The query does not clearly indicate General Liability or Property\n"
                f"  • The query is vague or missing key underwriting details\n"
                f"  • The previous response indicates missing or unavailable information\n"
                f"- If no clarification is needed, do NOT generate any clarification questions\n"
                f"- Then, generate exactly 3 follow-up questions\n"
                f"- Follow-up questions must be strictly related to underwriting topics\n"
                f"- Keep each question concise (under 100 characters)\n"
                f"- Return only the questions, one per line, without numbering or bullets"
            )
            
            response = await client.chat.completions.create(
                model=self.settings.openai_chat_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200,
            )
            text = response.choices[0].message.content or ""
            return [q.strip() for q in text.strip().split("\n") if q.strip()][:3]
        except Exception as e:
            logger.warning("follow_up_generation_failed", error=str(e))
            return []

    def clear_session(self, session_id: str) -> None:
        """Clear conversation session."""
        self.session_manager.clear_session(session_id)
        self.agents.pop(session_id, None)
        logger.info("session_cleared", session_id=session_id)
