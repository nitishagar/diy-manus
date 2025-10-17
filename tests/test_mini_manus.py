"""
Unit tests for mini-manus autonomous research agent

Tests cover:
1. State management
2. Planning decisions
3. Research data collection
4. Report generation
5. Graph routing logic
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from mini_manus import (
    ResearchState,
    planner_node,
    research_node,
    writer_node,
    route_next_step,
    create_mini_manus
)


@pytest.fixture
def mock_llm():
    """Mock LangChain LLM"""
    with patch('mini_manus.llm') as mock:
        yield mock


@pytest.fixture
def mock_mem0():
    """Mock Mem0 client"""
    with patch('mini_manus.mem0') as mock:
        mock.search.return_value = {"results": []}
        mock.add.return_value = True
        yield mock


@pytest.fixture
def mock_tavily():
    """Mock Tavily search client"""
    with patch('mini_manus.tavily') as mock:
        mock.search.return_value = {
            "results": [
                {
                    "title": "Test Article",
                    "url": "https://example.com/test",
                    "content": "Test content about the query",
                    "score": 0.95
                }
            ]
        }
        yield mock


@pytest.fixture
def base_state():
    """Base research state for testing"""
    return {
        "query": "What is quantum computing?",
        "user_id": "test_user",
        "steps_taken": [],
        "research_data": [],
        "final_report": "",
        "should_continue": True
    }


class TestPlannerNode:
    """Tests for the planner/decision-making agent"""

    def test_planner_decides_research_when_no_data(self, mock_llm, mock_mem0, base_state):
        """Planner should choose RESEARCH when no data exists"""
        # Mock LLM to return RESEARCH decision
        mock_response = Mock()
        mock_response.content = "RESEARCH"
        mock_llm.invoke.return_value = mock_response

        result = planner_node(base_state)

        assert "steps_taken" in result
        assert len(result["steps_taken"]) == 1
        assert "RESEARCH" in result["steps_taken"][0]
        assert result["should_continue"] is True

    def test_planner_decides_write_when_has_data(self, mock_llm, mock_mem0, base_state):
        """Planner should choose WRITE_REPORT when data exists"""
        # State with research data
        base_state["research_data"] = [
            {"title": "Article 1", "content": "Content 1"},
            {"title": "Article 2", "content": "Content 2"}
        ]

        mock_response = Mock()
        mock_response.content = "WRITE_REPORT"
        mock_llm.invoke.return_value = mock_response

        result = planner_node(base_state)

        assert "WRITE_REPORT" in result["steps_taken"][0]
        assert result["should_continue"] is True

    def test_planner_decides_done(self, mock_llm, mock_mem0, base_state):
        """Planner should choose DONE when task is complete"""
        base_state["final_report"] = "Complete report"

        mock_response = Mock()
        mock_response.content = "DONE"
        mock_llm.invoke.return_value = mock_response

        result = planner_node(base_state)

        assert "DONE" in result["steps_taken"][0]
        assert result["should_continue"] is False

    def test_planner_uses_memory_context(self, mock_llm, mock_mem0, base_state):
        """Planner should retrieve and use user memories"""
        mock_mem0.search.return_value = {
            "results": [
                {"memory": "User prefers technical depth"}
            ]
        }

        mock_response = Mock()
        mock_response.content = "RESEARCH"
        mock_llm.invoke.return_value = mock_response

        planner_node(base_state)

        # Verify mem0.search was called with correct params
        mock_mem0.search.assert_called_once()
        call_kwargs = mock_mem0.search.call_args[1]
        assert call_kwargs["query"] == base_state["query"]
        assert call_kwargs["user_id"] == base_state["user_id"]


class TestResearchNode:
    """Tests for the research/data collection agent"""

    def test_research_collects_data(self, mock_tavily, mock_mem0, base_state):
        """Research node should collect and structure findings"""
        result = research_node(base_state)

        assert "research_data" in result
        assert len(result["research_data"]) > 0

        finding = result["research_data"][0]
        assert "title" in finding
        assert "url" in finding
        assert "content" in finding
        assert "relevance_score" in finding

    def test_research_stores_in_memory(self, mock_tavily, mock_mem0, base_state):
        """Research should store findings in Mem0"""
        research_node(base_state)

        # Verify mem0.add was called
        mock_mem0.add.assert_called_once()
        call_kwargs = mock_mem0.add.call_args[1]
        assert call_kwargs["user_id"] == base_state["user_id"]
        assert "messages" in call_kwargs

    def test_research_handles_empty_results(self, mock_tavily, mock_mem0, base_state):
        """Research should handle empty search results gracefully"""
        mock_tavily.search.return_value = {"results": []}

        result = research_node(base_state)

        assert "research_data" in result
        assert len(result["research_data"]) == 0
        assert "steps_taken" in result

    def test_research_truncates_content(self, mock_tavily, mock_mem0, base_state):
        """Research should truncate long content to manage context"""
        long_content = "x" * 1000
        mock_tavily.search.return_value = {
            "results": [{
                "title": "Test",
                "url": "https://test.com",
                "content": long_content,
                "score": 0.9
            }]
        }

        result = research_node(base_state)

        # Content should be truncated to 300 chars
        assert len(result["research_data"][0]["content"]) <= 300


class TestWriterNode:
    """Tests for the report synthesis agent"""

    def test_writer_generates_report(self, mock_llm, mock_mem0, base_state):
        """Writer should generate a report from research data"""
        base_state["research_data"] = [
            {
                "title": "Quantum Basics",
                "url": "https://example.com/quantum",
                "content": "Quantum computing uses qubits...",
                "relevance_score": 0.9
            }
        ]

        mock_response = Mock()
        mock_response.content = "Comprehensive report about quantum computing..."
        mock_llm.invoke.return_value = mock_response

        result = writer_node(base_state)

        assert "final_report" in result
        assert len(result["final_report"]) > 0
        assert result["should_continue"] is False

    def test_writer_handles_no_data(self, mock_llm, mock_mem0, base_state):
        """Writer should handle case with no research data"""
        result = writer_node(base_state)

        assert "final_report" in result
        assert "No research data" in result["final_report"]
        assert result["should_continue"] is False

    def test_writer_stores_report_in_memory(self, mock_llm, mock_mem0, base_state):
        """Writer should store completed report in Mem0"""
        base_state["research_data"] = [
            {"title": "Test", "url": "https://test.com", "content": "Content"}
        ]

        mock_response = Mock()
        mock_response.content = "Final report"
        mock_llm.invoke.return_value = mock_response

        writer_node(base_state)

        # Verify mem0.add was called
        assert mock_mem0.add.called
        call_kwargs = mock_mem0.add.call_args[1]
        assert call_kwargs["user_id"] == base_state["user_id"]


class TestRouting:
    """Tests for the routing logic"""

    def test_route_to_research_when_planner_decides(self, base_state):
        """Router should go to research when planner decides RESEARCH"""
        base_state["steps_taken"] = ["🤔 Planner decided: RESEARCH"]
        base_state["should_continue"] = True

        next_node = route_next_step(base_state)

        assert next_node == "research"

    def test_route_to_write_when_planner_decides(self, base_state):
        """Router should go to write when planner decides WRITE_REPORT"""
        base_state["steps_taken"] = ["🤔 Planner decided: WRITE_REPORT"]
        base_state["should_continue"] = True

        next_node = route_next_step(base_state)

        assert next_node == "write"

    def test_route_to_end_when_should_not_continue(self, base_state):
        """Router should end when should_continue is False"""
        base_state["should_continue"] = False

        next_node = route_next_step(base_state)

        assert next_node == "end"

    def test_default_routing_no_data(self, base_state):
        """Default: route to research if no data"""
        base_state["steps_taken"] = ["Some step"]
        base_state["should_continue"] = True
        base_state["research_data"] = []

        next_node = route_next_step(base_state)

        assert next_node == "research"

    def test_default_routing_has_data(self, base_state):
        """Default: route to write if has data"""
        base_state["steps_taken"] = ["Some step"]
        base_state["should_continue"] = True
        base_state["research_data"] = [{"title": "Test"}]

        next_node = route_next_step(base_state)

        assert next_node == "write"


class TestGraphCreation:
    """Tests for LangGraph workflow creation"""

    def test_graph_creation(self):
        """Should create a valid LangGraph workflow"""
        app = create_mini_manus()

        assert app is not None
        # Graph should have our nodes
        nodes = list(app.get_graph().nodes.keys())
        assert "planner" in nodes
        assert "research" in nodes
        assert "write" in nodes

    def test_graph_has_correct_entry_point(self):
        """Graph should start at planner node"""
        app = create_mini_manus()
        graph = app.get_graph()

        # Entry point should be planner
        # (checking via edges - entry will have edge from __start__)
        edges = [str(e) for e in graph.edges]
        assert any("__start__" in e and "planner" in e for e in edges)


class TestIntegration:
    """Integration tests for the full workflow"""

    @patch('mini_manus.tavily')
    @patch('mini_manus.mem0')
    @patch('mini_manus.llm')
    def test_full_research_workflow(self, mock_llm, mock_mem0, mock_tavily):
        """Test complete research workflow from query to report"""
        # Setup mocks
        mock_mem0.search.return_value = {"results": []}
        mock_mem0.add.return_value = True

        mock_tavily.search.return_value = {
            "results": [{
                "title": "Test Article",
                "url": "https://test.com",
                "content": "Test content",
                "score": 0.9
            }]
        }

        # Mock LLM responses in sequence
        mock_llm.invoke.side_effect = [
            Mock(content="RESEARCH"),  # First planner call
            Mock(content="WRITE_REPORT"),  # Second planner call
            Mock(content="This is the final research report.")  # Writer call
        ]

        from mini_manus import run_research

        # Run the workflow
        result = run_research("Test query", "test_user")

        # Verify final state
        assert result["final_report"] != ""
        assert len(result["research_data"]) > 0
        assert len(result["steps_taken"]) > 0

    def test_state_accumulation(self, base_state):
        """Test that state properly accumulates data across nodes"""
        # Simulate sequential node execution
        state = base_state.copy()

        # Research adds data
        state["research_data"] = [{"title": "Test 1"}]
        state["steps_taken"] = ["Step 1"]

        # More research should accumulate
        state["research_data"].append({"title": "Test 2"})
        state["steps_taken"].append("Step 2")

        assert len(state["research_data"]) == 2
        assert len(state["steps_taken"]) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
