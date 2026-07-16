from typing import Optional
from pydantic import BaseModel


class DocumentUploadRequest(BaseModel):
    domain: str
    classification_level: str = "internal"
    project_id: Optional[str] = None
    submitter_id: str


class ExpertInputRequest(BaseModel):
    domain: str
    type: str = "case"
    title: str
    content: dict
    classification_level: str = "internal"
    # 保留该字段仅为兼容旧前端仍会发送 submitter_id 的请求体，后端不再信任/使用它，
    # 实际写入知识条目的提交人一律取自鉴权后的 SecurityContext.user_id。
    submitter_id: str = ""


class DbSyncTriggerRequest(BaseModel):
    source_system: str
    sync_mode: str = "incremental"
    domain: str


class CandidateResponse(BaseModel):
    candidateId: str
    status: str


class IngestionStatusResponse(BaseModel):
    candidateId: str
    status: str
    extractedKnowledgeIds: list[str] = []