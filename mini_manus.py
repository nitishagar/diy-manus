"""
Mini-Manus: A simplified autonomous research agent
Built with LangGraph + Mem0 in ~200 lines

Inspired by Manus (manus.im) - demonstrates:
1. Autonomous multi-step research
2. Memory across sessions
3. Transparent decision-making
"""

import os
from typing import TypedDict, List, Annotated
from operator import add

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from mem0 import MemoryClient
from tavily import TavilyClient

load_dotenv()

# Initialize services
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
mem0 = MemoryClient(api_key=os.getenv("MEM0_API_KEY"))
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


# State definition
class ResearchState(TypedDict):
    """Simple state for our research agent"""
    query: str
    user_id: str
    steps_taken: Annotated[List[str], add]  # Track what we've done
    research_data: Annotated[List[dict], add]  # Accumulate findings
    final_report: str
    should_continue: bool


def planner_node(state: ResearchState) -> dict:
    """
    The brain of our mini-Manus: decides what to do next

    Like Manus, this agent autonomously decides:
    - Do we need more research?
    - Do we have enough to write a report?
    - Should we stop?
    """
    query = state["query"]
    steps = state["steps_taken"]
    data_count = len(state["research_data"])

    # Retrieve memories about this user's research preferences
    memories = mem0.search(query=query, user_id=state["user_id"], limit=3)
    memory_context = "\n".join([m["memory"] for m in memories.get("results", [])]) if memories else "No prior context"

    system_prompt = f"""You are the planning agent for an autonomous research assistant (like Manus).

User Query: "{query}"
Steps completed: {len(steps)}
Research data collected: {data_count} sources

User's research preferences from memory:
{memory_context}

Your job: Decide the NEXT action. You have 3 options:

1. RESEARCH - We need more information (choose this if we have < 3 sources)
2. WRITE_REPORT - We have enough data, write the final report
3. DONE - Report is complete, end the task

Respond with ONLY one word: RESEARCH, WRITE_REPORT, or DONE

Current situation: {"No research yet" if data_count == 0 else f"{data_count} sources gathered"}"""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content="What should I do next?")
    ])

    decision = response.content.strip().upper()

    # Log the decision (Manus shows its thinking)
    step_desc = f"🤔 Planner decided: {decision}"

    return {
        "steps_taken": [step_desc],
        "should_continue": decision != "DONE"
    }


def research_node(state: ResearchState) -> dict:
    """
    The researcher: finds information like Manus does

    Uses web search to gather data autonomously
    """
    query = state["query"]

    print(f"\n🔍 Researching: {query}")

    # Perform web search
    results = tavily.search(query=query, max_results=3, search_depth="advanced")

    findings = []
    for r in results.get("results", []):
        findings.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", "")[:300],  # Truncate
            "relevance_score": r.get("score", 0)
        })

    # Store this research session in memory
    mem0.add(
        messages=[
            {"role": "user", "content": f"Research: {query}"},
            {"role": "assistant", "content": f"Found {len(findings)} sources"}
        ],
        user_id=state["user_id"]
    )

    step_desc = f"📚 Researched and found {len(findings)} sources"

    return {
        "research_data": findings,
        "steps_taken": [step_desc]
    }


def writer_node(state: ResearchState) -> dict:
    """
    The writer: synthesizes findings into a report

    Like Manus creating content from research
    """
    query = state["query"]
    data = state["research_data"]

    print(f"\n✍️  Writing report...")

    if not data:
        return {
            "final_report": "No research data available.",
            "steps_taken": ["⚠️  No data to write about"],
            "should_continue": False
        }

    # Build context from research
    research_text = "\n\n".join([
        f"Source {i+1}: {d['title']}\n{d['content']}\nURL: {d['url']}"
        for i, d in enumerate(data)
    ])

    system_prompt = f"""You are a research report writer.

User asked: "{query}"

Write a comprehensive research report that:
1. Answers the user's question directly
2. Synthesizes information from multiple sources
3. Cites sources properly
4. Is clear and actionable

Keep it concise but informative (3-4 paragraphs)."""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Research findings:\n\n{research_text}")
    ])

    report = response.content

    # Store the completed research in memory
    mem0.add(
        messages=[
            {"role": "user", "content": query},
            {"role": "assistant", "content": f"Completed research report: {report[:200]}..."}
        ],
        user_id=state["user_id"]
    )

    return {
        "final_report": report,
        "steps_taken": ["📝 Report written"],
        "should_continue": False
    }


def route_next_step(state: ResearchState) -> str:
    """
    Router: determines which node to execute next

    This is key to autonomous behavior - the agent decides its own path
    """
    if not state["should_continue"]:
        return "end"

    # Check what the planner decided
    last_step = state["steps_taken"][-1] if state["steps_taken"] else ""

    if "RESEARCH" in last_step:
        return "research"
    elif "WRITE_REPORT" in last_step:
        return "write"
    else:
        # Default: if we have no data, research; otherwise write
        if len(state["research_data"]) == 0:
            return "research"
        else:
            return "write"


def create_mini_manus():
    """Build the LangGraph workflow"""
    workflow = StateGraph(ResearchState)

    # Add nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("research", research_node)
    workflow.add_node("write", writer_node)

    # Define flow
    workflow.set_entry_point("planner")

    # Planner routes to research/write/end
    workflow.add_conditional_edges(
        "planner",
        route_next_step,
        {
            "research": "research",
            "write": "write",
            "end": END
        }
    )

    # After research, go back to planner
    workflow.add_edge("research", "planner")

    # After writing, end
    workflow.add_edge("write", END)

    # Compile with checkpointing (for durability like Manus)
    return workflow.compile(checkpointer=MemorySaver())


def run_research(query: str, user_id: str = "demo_user"):
    """Execute a research task autonomously"""

    print("="*60)
    print(f"🤖 Mini-Manus Autonomous Researcher")
    print("="*60)
    print(f"\nQuery: {query}")
    print(f"User: {user_id}\n")

    app = create_mini_manus()

    initial_state = {
        "query": query,
        "user_id": user_id,
        "steps_taken": [],
        "research_data": [],
        "final_report": "",
        "should_continue": True
    }

    # Run the workflow
    final_state = app.invoke(
        initial_state,
        config={"configurable": {"thread_id": f"research_{user_id}"}}
    )

    # Display results (like Manus task replay)
    print("\n" + "="*60)
    print("📋 TASK EXECUTION SUMMARY")
    print("="*60)

    print("\nSteps Taken:")
    for i, step in enumerate(final_state["steps_taken"], 1):
        print(f"  {i}. {step}")

    print(f"\n📊 Research Data: {len(final_state['research_data'])} sources")

    print("\n" + "="*60)
    print("📄 FINAL REPORT")
    print("="*60)
    print(final_state["final_report"])

    print("\n" + "="*60)
    print("🔗 SOURCES")
    print("="*60)
    for i, source in enumerate(final_state["research_data"], 1):
        print(f"\n{i}. {source['title']}")
        print(f"   {source['url']}")
        print(f"   Relevance: {source['relevance_score']:.2f}")

    print("\n✅ Research complete!\n")

    return final_state


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python mini_manus.py \"Your research query here\"")
        print("\nExample:")
        print('  python mini_manus.py "What are the latest developments in quantum computing?"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    run_research(query)
