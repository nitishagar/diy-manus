"""
Test that all imports work correctly
This validates the code structure without requiring API keys
"""

def test_imports():
    """Test that mini_manus module can be imported"""
    try:
        import mini_manus
        assert hasattr(mini_manus, 'ResearchState')
        assert hasattr(mini_manus, 'planner_node')
        assert hasattr(mini_manus, 'research_node')
        assert hasattr(mini_manus, 'writer_node')
        assert hasattr(mini_manus, 'create_mini_manus')
        assert hasattr(mini_manus, 'run_research')
    except ImportError as e:
        assert False, f"Import failed: {e}"


def test_type_definitions():
    """Test that TypedDict state is properly defined"""
    from mini_manus import ResearchState

    # Should have all required keys
    required_keys = {'query', 'user_id', 'steps_taken', 'research_data',
                     'final_report', 'should_continue'}

    # TypedDict annotations
    assert hasattr(ResearchState, '__annotations__')
    annotations = ResearchState.__annotations__
    assert all(key in annotations for key in required_keys)


if __name__ == "__main__":
    test_imports()
    test_type_definitions()
    print("✅ All import tests passed")
