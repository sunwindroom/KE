"""针对“数据接入 - 上传文档”接口的回归测试。

历史 bug：路由直接把 `await file.read()` 得到的 bytes 传给
`minio_client.put_object(...)`，而 minio-py 要求 data 参数是一个具备
`.read()` 方法的流对象。bytes 没有 `.read()`，导致 minio-py 内部
`getattr(data, "read")` 抛出 AttributeError，每一次文档上传都会 100% 失败
（对应前端报错“上传失败”）。

这里用一个模拟 minio 客户端的 fake（严格复刻 minio-py 对 data 参数的
校验逻辑）来验证：接口现在传给 put_object 的是一个可读流对象，而不是裸
bytes；同时验证 minio_client 为 None（对象存储未就绪/不可用）时会返回
明确的业务错误，而不是让请求以未处理异常的方式崩溃。
"""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.auth import SecurityContext
from app.core.exceptions import BusinessException, ServiceUnavailableException
from app.services.ingestion.router import upload_document


class _FakeUploadFile:
    def __init__(self, filename: str, content: bytes, content_type: str):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content


class _StrictFakeMinio:
    """严格复刻 minio-py 对 `data` 参数的校验：必须具备可调用的 read()。"""

    def __init__(self):
        self.calls = []

    def put_object(self, bucket_name, object_name, data, length, content_type=None, **kwargs):
        if not callable(getattr(data, "read", None)):
            raise AttributeError("'bytes' object has no attribute 'read'")
        self.calls.append((bucket_name, object_name, data.read(), length, content_type))


def _make_ctx() -> SecurityContext:
    return SecurityContext(
        user_id="u1",
        user_name="tester",
        role="engineer",
        domain_scope=["aerospace"],
        max_classification_level="confidential",
    )


@pytest.mark.asyncio
async def test_upload_document_passes_stream_not_bytes(monkeypatch):
    fake_minio = _StrictFakeMinio()
    monkeypatch.setattr("app.services.ingestion.router.get_minio_client", lambda: fake_minio)
    monkeypatch.setattr("app.services.ingestion.router._publish_candidate", AsyncMock())

    fake_db = MagicMock()
    fake_db.add = MagicMock()
    fake_db.commit = AsyncMock()

    upload_file = _FakeUploadFile(
        filename="故障报告.docx",
        content=b"fake docx binary content",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    result = await upload_document(
        domain="aerospace",
        classification_level="internal",
        project_id=None,
        file=upload_file,
        db=fake_db,
        ctx=_make_ctx(),
    )

    # 修复前：上面这行调用会直接抛出 AttributeError，测试会在此处失败。
    assert result.data.status == "pending"
    assert len(fake_minio.calls) == 1
    bucket, object_name, stored_content, length, content_type = fake_minio.calls[0]
    assert bucket == "phm-documents"
    assert stored_content == b"fake docx binary content"
    assert length == len(b"fake docx binary content")
    fake_db.add.assert_called_once()
    fake_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_document_rejects_unsupported_extension():
    upload_file = _FakeUploadFile(filename="virus.exe", content=b"x", content_type="application/octet-stream")
    with pytest.raises(BusinessException):
        await upload_document(
            domain="aerospace",
            classification_level="internal",
            project_id=None,
                file=upload_file,
            db=MagicMock(),
            ctx=_make_ctx(),
        )


@pytest.mark.asyncio
async def test_upload_document_reports_clear_error_when_storage_unavailable(monkeypatch):
    monkeypatch.setattr("app.services.ingestion.router.get_minio_client", lambda: None)

    upload_file = _FakeUploadFile(
        filename="report.docx",
        content=b"content",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    with pytest.raises(ServiceUnavailableException):
        await upload_document(
            domain="aerospace",
            classification_level="internal",
            project_id=None,
                file=upload_file,
            db=MagicMock(),
            ctx=_make_ctx(),
        )
