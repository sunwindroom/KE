import difflib

from app.services.governance import conflict_service


def test_similarity_threshold_flags_near_duplicate_titles():
    ratio = difflib.SequenceMatcher(None, "液压泵密封老化处置流程", "液压泵密封老化处理流程").ratio()
    assert ratio >= conflict_service.SIMILARITY_THRESHOLD


def test_similarity_threshold_does_not_flag_unrelated_titles():
    ratio = difflib.SequenceMatcher(None, "液压泵密封老化处置流程", "变频器过流保护规则集").ratio()
    assert ratio < conflict_service.SIMILARITY_THRESHOLD


def test_active_statuses_excludes_deprecated_and_archived():
    assert "deprecated" not in conflict_service.ACTIVE_STATUSES
    assert "archived" not in conflict_service.ACTIVE_STATUSES
    assert "draft" in conflict_service.ACTIVE_STATUSES
    assert "published" in conflict_service.ACTIVE_STATUSES
