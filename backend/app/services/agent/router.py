import json
import logging
from typing import Optional
from uuid import uuid4
from datetime import datetime

from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.postgresql import get_db
from app.core.auth import SecurityContext
from app.core.exceptions import ResourceNotFoundException, BusinessException
from app.middleware.auth import get_current_user
from app.models.models import AgentTask
from app.schemas.common import ApiResponse
from app.services.agent.agent_service import AGENT_RUNNERS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["Agent智能体"])


class TaskSubmitRequest(BaseModel):
    agent_type: str
    input: dict
    domain: Optional[str] = None
    # 兼容旧前端仍会发送该字段，但后端不再信任它——一律取自鉴权后的 ctx.user_id。
    submitter_id: str = ""


class ConfirmRequest(BaseModel):
    # 同上：确认人不再信任客户端传入值，取自鉴权后的 ctx.user_id。
    confirmer_id: str = ""
    decision: str
    comment: Optional[str] = None


async def _run_agent_task(task_id: str, agent_type: str, query: str, domain: Optional[str], ctx: SecurityContext) -> None:
    from app.db.postgresql import async_session_factory

    async with async_session_factory() as db:
        result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            return
        try:
            runner = AGENT_RUNNERS[agent_type]
            trace, final_result, needs_confirmation = await runner(db, query, domain, ctx)
            task.trace = json.dumps(trace, ensure_ascii=False)
            task.final_result = final_result
            task.human_confirmation_required = 1 if needs_confirmation else 0
            task.status = "waiting_confirmation" if needs_confirmation else "completed"
            if not needs_confirmation:
                task.completed_at = datetime.now()
        except Exception as exc:
            logger.exception("Agent 任务 %s 执行失败", task_id)
            task.status = "failed"
            task.final_result = f"任务执行失败：{exc}"
            task.trace = json.dumps([{"step": 0, "action": "执行异常", "output": str(exc)}], ensure_ascii=False)
            task.completed_at = datetime.now()
        await db.commit()


@router.post("/task/submit", response_model=ApiResponse)
async def submit_task(
    req: TaskSubmitRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    if req.agent_type not in AGENT_RUNNERS:
        raise BusinessException(code=40001, message=f"未知的 agent_type，支持的类型：{', '.join(AGENT_RUNNERS.keys())}")

    query = str(req.input.get("query") or req.input.get("question") or "").strip()
    if not query:
        raise BusinessException(code=40001, message="input 中需要提供 query 字段")

    task_id = f"AG{datetime.now().strftime('%Y%m%d')}{uuid4().hex[:4].upper()}"
    task = AgentTask(
        id=task_id,
        agent_type=req.agent_type,
        input_data=json.dumps(req.input, ensure_ascii=False),
        domain=req.domain,
        submitter_id=ctx.user_id,
        status="running",
    )
    db.add(task)
    await db.commit()

    background_tasks.add_task(_run_agent_task, task_id, req.agent_type, query, req.domain, ctx)
    return ApiResponse(data={"taskId": task_id, "status": "running"})


@router.get("/task/{task_id}/status", response_model=ApiResponse)
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise ResourceNotFoundException("任务不存在")

    current_step = ""
    if task.trace:
        try:
            steps = json.loads(task.trace)
            if steps:
                current_step = steps[-1]["action"]
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

    return ApiResponse(data={"taskId": task.id, "status": task.status, "currentStep": current_step})


@router.get("/task/{task_id}/result", response_model=ApiResponse)
async def get_task_result(task_id: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise ResourceNotFoundException("任务不存在")

    trace = []
    if task.trace:
        try:
            trace = json.loads(task.trace)
        except json.JSONDecodeError:
            trace = []

    return ApiResponse(data={"taskId": task.id, "trace": trace, "finalResult": task.final_result or ""})


@router.post("/task/{task_id}/confirm", response_model=ApiResponse)
async def confirm_task(task_id: str, req: ConfirmRequest, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise ResourceNotFoundException("任务不存在")
    if task.status != "waiting_confirmation":
        raise BusinessException(code=40001, message=f"任务当前状态为 {task.status}，不处于待确认状态")
    if req.decision not in ("approved", "rejected"):
        raise BusinessException(code=40001, message="decision 必须是 approved 或 rejected")

    task.status = "confirmed" if req.decision == "approved" else "rejected"
    task.completed_at = datetime.now()

    from app.models.models import AuditLog
    db.add(AuditLog(
        id=f"AL{uuid4().hex[:12]}", user_id=ctx.user_id, action=f"agent_task_{req.decision}",
        resource_type="agent_task", resource_id=task_id, detail=req.comment or "",
    ))
    await db.commit()
    return ApiResponse(data={"taskId": task_id, "status": task.status})


@router.get("/tasks", response_model=ApiResponse)
async def list_tasks(
    submitter_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    stmt = select(AgentTask).order_by(AgentTask.created_at.desc()).limit(50)
    if submitter_id:
        stmt = stmt.where(AgentTask.submitter_id == submitter_id)
    result = await db.execute(stmt)
    return ApiResponse(data=[
        {
            "taskId": t.id, "agentType": t.agent_type, "status": t.status,
            "domain": t.domain, "createdAt": t.created_at.isoformat(),
        }
        for t in result.scalars().all()
    ])


@router.get("/stats", response_model=ApiResponse)
async def get_agent_stats(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    from datetime import timedelta

    cutoff = datetime.now() - timedelta(hours=24)
    total_24h_result = await db.execute(select(func.count()).select_from(AgentTask).where(AgentTask.created_at >= cutoff))
    total_24h = total_24h_result.scalar() or 0

    completed_result = await db.execute(
        select(func.avg(func.extract("epoch", AgentTask.completed_at) - func.extract("epoch", AgentTask.created_at)))
        .where(AgentTask.completed_at.is_not(None), AgentTask.created_at >= cutoff)
    )
    avg_seconds = completed_result.scalar()

    by_type_result = await db.execute(
        select(AgentTask.agent_type, func.count()).where(AgentTask.created_at >= cutoff).group_by(AgentTask.agent_type)
    )
    by_type = {row[0]: row[1] for row in by_type_result.all()}

    return ApiResponse(data={
        "calls24h": total_24h,
        "avgDurationSeconds": round(avg_seconds, 1) if avg_seconds is not None else None,
        "byType": by_type,
        "availableAgentTypes": list(AGENT_RUNNERS.keys()),
    })
