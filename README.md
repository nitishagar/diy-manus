# Mini-Manus: Build Your Own Autonomous Research Agent in 30 Minutes

A simplified version of [Manus](https://manus.im) - demonstrating autonomous AI agents with LangGraph + Mem0.

**What Manus does**: Autonomously breaks down complex tasks, executes multi-step workflows, learns from experience

**What we'll build**: A mini research agent that autonomously:
1. Plans its own research strategy
2. Searches the web for information
3. Synthesizes findings into reports
4. Learns user preferences across sessions

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API keys
cp .env.example .env
# Edit .env with your keys

# 3. Run a research query
python mini_manus.py "What are the latest developments in quantum computing?"
```

## Architecture

```
┌──────────┐
│  Planner │ ← Decides next action autonomously
└────┬─────┘
     │
     ├─→ Research Node (web search)
     │
     └─→ Writer Node (synthesize report)
```

### Key Patterns from Manus

1. **Autonomous Decision-Making**: The planner decides what to do next (research vs. write vs. done)
2. **Multi-Step Execution**: Breaks complex tasks into steps
3. **Transparent Thinking**: Shows each decision it makes (like Manus replay feature)
4. **Memory Across Sessions**: Learns user preferences via Mem0

## Development

```bash
# Install dev dependencies
make install

# Run linting
make lint

# Run tests
make test

# Run all checks
make check

# Format code
make format
```

## Testing

Comprehensive unit tests cover:
- Planning/decision logic
- Research data collection
- Report synthesis
- Graph routing
- Memory integration
- Full workflow integration

```bash
# Run tests with coverage
pytest tests/ -v --cov=mini_manus --cov-report=term-missing

# Current coverage: ~85%
```

## Code Quality

- **Linting**: flake8 + mypy for type checking
- **Formatting**: black (100 char line length)
- **Testing**: pytest with mocking for external APIs
- **Type Hints**: Full type annotations

## API Keys Required

- **OpenAI** (gpt-4o-mini): https://platform.openai.com
- **Mem0** (memory layer): https://app.mem0.ai
- **Tavily** (web search): https://tavily.com

All have free tiers to get started.

## How It Works

### 1. Planner Node (The Brain)

```python
def planner_node(state):
    # Retrieves user preferences from Mem0
    # Decides: RESEARCH, WRITE_REPORT, or DONE
    # Returns decision to router
```

**Like Manus**: Makes autonomous decisions about next steps

### 2. Research Node (The Gatherer)

```python
def research_node(state):
    # Searches web via Tavily
    # Collects structured findings
    # Stores in Mem0 for future reference
```

**Like Manus**: Autonomously gathers information from multiple sources

### 3. Writer Node (The Synthesizer)

```python
def writer_node(state):
    # Analyzes research data
    # Generates comprehensive report
    # Stores completed work in memory
```

**Like Manus**: Creates deliverables from raw information

### 4. LangGraph Orchestration

```python
workflow = StateGraph(ResearchState)
workflow.add_node("planner", planner_node)
workflow.add_node("research", research_node)
workflow.add_node("write", writer_node)
# Planner routes to research/write/end dynamically
```

**Like Manus**: Explicit, visual workflow that adapts based on state

## What's Different from Real Manus?

| Feature | Manus | Mini-Manus |
|---------|-------|------------|
| Scope | Code, data analysis, content, research | Research only |
| UI | Web interface with replay | CLI output |
| Complexity | Multi-hour tasks | ~30 second tasks |
| Cost | $2/task | ~$0.10/task |
| Code | Production-grade | Educational (~200 lines) |

**Mini-Manus is for learning the patterns.** The principles scale to production systems.

## Extending Mini-Manus

Ideas to make it more Manus-like:

1. **Add more specialist agents**:
   ```python
   workflow.add_node("fact_checker", fact_check_node)
   workflow.add_node("citation_validator", citation_node)
   ```

2. **Implement task replay**:
   ```python
   # Save each step's state for replay
   checkpointer.save(step_id, state)
   ```

3. **Add human-in-the-loop**:
   ```python
   workflow.add_node("approval", await_human_approval)
   ```

4. **Multi-modal support**:
   ```python
   workflow.add_node("image_analyzer", process_images)
   ```

## Learning Resources

- **LangGraph Docs**: https://docs.langchain.com/docs/langgraph
- **Mem0 Docs**: https://docs.mem0.ai
- **Manus Guide**: https://github.com/hodorwang/manus-guide
- **Original Manus**: https://manus.im

## License

MIT - Educational purposes

---

**Built as a tutorial for understanding autonomous AI agent patterns inspired by Manus.**
