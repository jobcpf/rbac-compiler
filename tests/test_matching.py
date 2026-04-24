"""Unit tests for the three pure match functions."""

from rbac_compiler.matching import grade_match, scope_match, vertical_match


class TestGradeMatch:
    def test_more_privileged_matches(self):
        assert grade_match(1, 2) is True

    def test_equal_privilege_matches(self):
        assert grade_match(2, 2) is True

    def test_less_privileged_does_not_match(self):
        assert grade_match(3, 2) is False

    def test_extremes(self):
        assert grade_match(0, 20) is True
        assert grade_match(20, 0) is False


class TestVerticalMatch:
    def test_agent_any_matches_any_specific(self):
        assert vertical_match("any", "tech") is True
        assert vertical_match("any", "finance") is True

    def test_dir_any_matches_any_specific(self):
        assert vertical_match("tech", "any") is True
        assert vertical_match("engineering", "any") is True

    def test_both_any(self):
        assert vertical_match("any", "any") is True

    def test_specific_equal(self):
        assert vertical_match("tech", "tech") is True

    def test_specific_mismatch(self):
        assert vertical_match("tech", "finance") is False


class TestScopeMatch:
    def test_agent_global_matches_any_specific(self):
        assert scope_match("global", "uk") is True
        assert scope_match("global", "mz") is True

    def test_dir_global_matches_any_specific(self):
        assert scope_match("uk", "global") is True
        assert scope_match("mz", "global") is True

    def test_both_global(self):
        assert scope_match("global", "global") is True

    def test_specific_equal(self):
        assert scope_match("uk", "uk") is True

    def test_specific_mismatch(self):
        assert scope_match("uk", "mz") is False

    def test_any_is_not_scope_wildcard(self):
        # 'any' is the vertical wildcard, not the scope wildcard.
        # If somehow 'any' ends up in a scope field it must NOT match.
        assert scope_match("any", "uk") is False
        assert scope_match("uk", "any") is False
