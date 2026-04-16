#!/usr/bin/env python3
"""
Simple script to query the Bedrock KB agent.
Usage: python query.py "your question here"
"""
import asyncio
import sys
from app.bedrock_kb_agent import BedrockKBAgent
from app.session_manager import SessionManager


async def main():
    if len(sys.argv) < 2:
        print("Usage: python query.py \"your question\"")
        print("Example: python query.py \"What are the main topics?\"")
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    
    print(f"Query: {query}")
    print()
    
    session_manager = SessionManager()
    session_id = session_manager.create_session()
    agent = BedrockKBAgent(session_manager)
    
    answer, sources, follow_ups = await agent.query(
        session_id=session_id,
        query=query
    )
    
    print("="*60)
    print("ANSWER")
    print("="*60)
    print(answer)
    print()
    
    if sources:
        print("="*60)
        print("SOURCES")
        print("="*60)
        for i, source in enumerate(sources, 1):
            print(f"{i}. {source}")
        print()
    
    if follow_ups:
        print("="*60)
        print("FOLLOW-UP QUESTIONS")
        print("="*60)
        for i, q in enumerate(follow_ups, 1):
            print(f"{i}. {q}")


if __name__ == '__main__':
    asyncio.run(main())
