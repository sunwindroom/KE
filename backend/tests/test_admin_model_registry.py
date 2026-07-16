from httpx import AsyncClient, ASGITransport

from app.main import app
from app.middleware.auth import get_current_user
from app.core.auth import SecurityContext
from app.config import get_settings
from app.services.admin.router import _mask_secret


def _admin_ctx() -> SecurityContext:
    return SecurityContext(
        user_id="admin1",
        user_name="admin",
        role="admin",
        domain_scope=["energy", "transportation", "aerospace", "general"],
        max_classification_level="secret",
    )


def test_mask_secret_keeps_last_four_chars_only():
    assert _mask_secret("") == ""
    assert _mask_secret("abcd") == "****"
    assert _mask_secret("sk-1234567890abcd") == "*" * 13 + "abcd"


async def test_model_registry_reports_fallback_when_no_api_key():
    get_settings.cache_clear()
    app.dependency_overrides[get_current_user] = _admin_ctx
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/admin/model/registry")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        entries = body["data"]
        assert {"llm", "embedding"} == {e["kind"] for e in entries}
        for entry in entries:
            # 测试环境默认没有设置 LLM_API_KEY，因此两个条目都应报告为规则降级，
            # 且不应该把明文密钥泄露出去（未配置时打码结果为空字符串）。
            assert entry["configured"] is False
            assert entry["status"] == "fallback_rule_based"
            assert entry["apiKeyPreview"] == ""
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_model_registry_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/admin/model/registry")
    assert resp.status_code in (401, 403)
