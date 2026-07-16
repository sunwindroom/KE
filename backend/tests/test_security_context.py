from app.core.auth import SecurityContext


def _ctx(role="engineer", domain_scope=("energy",), max_level="internal"):
    return SecurityContext(
        user_id="u1", user_name="test", role=role,
        domain_scope=list(domain_scope), max_classification_level=max_level,
    )


def test_can_access_classification_allows_equal_or_lower():
    ctx = _ctx(max_level="confidential")
    assert ctx.can_access_classification("public")
    assert ctx.can_access_classification("internal")
    assert ctx.can_access_classification("confidential")


def test_can_access_classification_denies_higher():
    ctx = _ctx(max_level="internal")
    assert ctx.can_access_classification("confidential") is False
    assert ctx.can_access_classification("secret") is False


def test_can_access_classification_unknown_level_defaults_deny():
    ctx = _ctx(max_level="internal")
    assert ctx.can_access_classification("not_a_real_level") is False


def test_has_domain_matches_explicit_scope():
    ctx = _ctx(domain_scope=("energy", "transportation"))
    assert ctx.has_domain("energy")
    assert ctx.has_domain("transportation")
    assert ctx.has_domain("aerospace") is False


def test_has_domain_general_scope_is_wildcard():
    ctx = _ctx(domain_scope=("general",))
    assert ctx.has_domain("aerospace")
    assert ctx.has_domain("energy")


def test_has_role_and_is_admin():
    ctx = _ctx(role="admin")
    assert ctx.has_role("admin", "expert")
    assert ctx.is_admin() is True

    engineer_ctx = _ctx(role="engineer")
    assert engineer_ctx.has_role("admin", "expert") is False
    assert engineer_ctx.is_admin() is False
