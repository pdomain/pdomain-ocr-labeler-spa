"""Test that specs/16-milestones.md contains properly formatted M9.1 and M9.2 sections."""


def test_m9_1_section_exists_with_testids():
    """M9.1 acceptance tests reference rotate-cw-button and rotation-badge testids."""
    with open("specs/16-milestones.md") as f:
        content = f.read()

    # Check M9.1 section exists
    assert "## M9.1" in content, "M9.1 section not found"

    # Extract M9.1 section (from M9.1 to next ## or end of file)
    m91_start = content.find("## M9.1")
    m91_end = content.find("\n## ", m91_start + 1)
    if m91_end == -1:
        m91_end = len(content)
    m91_section = content[m91_start:m91_end]

    # Check for required testids in M9.1 acceptance tests
    assert "rotate-cw-button" in m91_section, "rotate-cw-button testid not found in M9.1 acceptance tests"
    assert "rotation-badge" in m91_section, "rotation-badge testid not found in M9.1 acceptance tests"
    assert "**Acceptance tests.**" in m91_section, "M9.1 missing acceptance tests section"


def test_m9_2_section_exists_with_testids():
    """M9.2 acceptance tests reference auto-rotate-checkbox and auto-rotate-method-select testids."""
    with open("specs/16-milestones.md") as f:
        content = f.read()

    # Check M9.2 section exists
    assert "## M9.2" in content, "M9.2 section not found"

    # Extract M9.2 section (from M9.2 to next ## or end of file)
    m92_start = content.find("## M9.2")
    m92_end = content.find("\n## ", m92_start + 1)
    if m92_end == -1:
        m92_end = len(content)
    m92_section = content[m92_start:m92_end]

    # Check for required testids in M9.2 acceptance tests
    assert "auto-rotate-checkbox" in m92_section, "auto-rotate-checkbox not in M9.2"
    assert "auto-rotate-method-select" in m92_section, "auto-rotate-method-select not in M9.2"
    assert "**Acceptance tests.**" in m92_section, "M9.2 missing acceptance tests"


def test_no_existing_milestones_modified():
    """No existing milestone entries (M0-M9) should be modified."""
    with open("specs/16-milestones.md") as f:
        content = f.read()

    # Count occurrences of milestone headers
    m0_count = content.count("## M0 —")
    m1_count = content.count("## M1 —")
    m9_count = content.count("## M9 —")

    # Each should appear exactly once (not counting M9.1, M9.2, M9.5)
    assert m0_count == 1, f"M0 section appears {m0_count} times, expected 1"
    assert m1_count == 1, f"M1 section appears {m1_count} times, expected 1"
    assert m9_count == 1, f"M9 section appears {m9_count} times, expected 1"
