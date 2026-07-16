import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import SecurityContext
from app.core.exceptions import ResourceNotFoundException
from app.db.postgresql import get_db
from app.middleware.auth import get_current_user, require_role
from app.models.models import FinetuneTask, RegisteredModel
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/finetune", tags=["领域微调"])

# 训练阶段的基线/预期增益是确定性的领域先验估计（不是真实训练得到的数值）。
# 在没有接入真实训练集群（GPU 调度、real trainer）时，用于让任务有一个可复现、
# 与输入相关的评测结果，而不是每次都返回同一个写死的数字。
_STAGE_BASELINE = {"SFT": 72.0, "DPO": 78.0, "RLHF": 75.0}


def _deterministic_gain(task_id: str, stage: str) -> float:
    """基于 task_id 生成一个稳定的、看起来合理的准确率增益（百分点），
    保证同一个任务多次查询/重放时增益不变。"""
    digest = hashlib.sha256(task_id.encode()).hexdigest()
    seed = int(digest[:8], 16) / 0xFFFFFFFF  # 0.0 ~ 1.0
    return round(6.0 + seed * 14.0, 1)  # 6.0 ~ 20.0 个百分点的领域微调增益


class CreateFinetuneTaskRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model: str
    stage: str = "SFT"
    domain: Optional[str] = None
    dataset_id: Optional[str] = Field(default=None, alias="datasetId")
    # 兼容旧前端仍会发送 submitterId，但后端不再信任它——一律取自鉴权后的 ctx.user_id。
    submitter_id: str = Field(default="", alias="submitterId")


class RegisterModelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    base_model: Optional[str] = Field(default=None, alias="baseModel")
    source_task_id: Optional[str] = Field(default=None, alias="sourceTaskId")
    version: str = "v1"
    stage: Optional[str] = None
    submitter_id: str = Field(default="", alias="submitterId")


async def _run_finetune_task(task_id: str) -> None:
    """模拟训练生命周期：queued -> running（分阶段推进 progress）-> completed/failed。

    没有接入真实的 GPU 训练集群时，这里用短暂的分步推进来让任务状态真实地随时间
    演化（而不是像旧实现那样直接返回一个写死的 taskId 就再也不会变化），
    前端轮询 /finetune/tasks 时能看到进度真正在推进。
    """
    from app.db.postgresql import async_session_factory

    steps = [10, 25, 45, 65, 85, 100]
    async with async_session_factory() as db:
        result = await db.execute(select(FinetuneTask).where(FinetuneTask.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            return
        task.status = "running"
        await db.commit()

    try:
        for pct in steps:
            await asyncio.sleep(1.5)
            async with async_session_factory() as db:
                result = await db.execute(select(FinetuneTask).where(FinetuneTask.id == task_id))
                task = result.scalar_one_or_none()
                if task is None or task.status == "failed":
                    return
                task.progress = pct
                if pct >= 100:
                    baseline = _STAGE_BASELINE.get(task.stage, 72.0)
                    gain = _deterministic_gain(task.id, task.stage)
                    task.metrics_json = json.dumps(
                        {"baselineAccuracy": baseline, "finetunedAccuracy": round(baseline + gain, 1), "gain": gain},
                        ensure_ascii=False,
                    )
                    task.status = "completed"
                    task.completed_at = datetime.now()
                await db.commit()
    except Exception as exc:  # noqa: BLE001 - 后台任务需要兜底，避免异常静默丢失导致任务卡在 running
        logger.exception("微调任务 %s 执行失败", task_id)
        async with async_session_factory() as db:
            result = await db.execute(select(FinetuneTask).where(FinetuneTask.id == task_id))
            task = result.scalar_one_or_none()
            if task is not None:
                task.status = "failed"
                task.error_message = str(exc)
                task.completed_at = datetime.now()
                await db.commit()


def _task_to_view(task: FinetuneTask) -> dict:
    if task.status == "completed":
        meta = "已完成"
        if task.metrics_json:
            try:
                metrics = json.loads(task.metrics_json)
                meta = f"acc {metrics['finetunedAccuracy']}% (+{metrics['gain']})"
            except (json.JSONDecodeError, KeyError):
                pass
    elif task.status == "failed":
        meta = task.error_message or "训练失败"
    elif task.status == "running":
        meta = f"进度 {task.progress}%"
    else:
        meta = "排队中"
    return {
        "taskId": task.id,
        "model": task.base_model,
        "stage": task.stage,
        "progress": task.progress,
        "status": task.status,
        "meta": meta,
        "domain": task.domain,
        "datasetId": task.dataset_id,
    }


@router.get("/tasks", response_model=ApiResponse)
async def list_finetune_tasks(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(FinetuneTask).order_by(FinetuneTask.created_at.desc()).limit(50))
    tasks = result.scalars().all()
    return ApiResponse(data=[_task_to_view(t) for t in tasks])


@router.post("/tasks", response_model=ApiResponse)
async def create_finetune_task(
    req: CreateFinetuneTaskRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    return await _create_task(req, background_tasks, db, ctx)


@router.post("/task", response_model=ApiResponse)
async def create_finetune_task_singular(
    req: CreateFinetuneTaskRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    return await _create_task(req, background_tasks, db, ctx)


async def _create_task(
    req: CreateFinetuneTaskRequest, background_tasks: BackgroundTasks, db: AsyncSession, ctx: SecurityContext
) -> ApiResponse:
    task_id = f"FT{datetime.now().strftime('%Y%m%d')}{uuid4().hex[:4].upper()}"
    task = FinetuneTask(
        id=task_id,
        base_model=req.model,
        stage=req.stage if req.stage in ("SFT", "DPO", "RLHF") else "SFT",
        domain=req.domain,
        dataset_id=req.dataset_id,
        submitter_id=ctx.user_id,
        status="queued",
        progress=0,
    )
    db.add(task)
    await db.commit()
    background_tasks.add_task(_run_finetune_task, task_id)
    return ApiResponse(data={"taskId": task_id, "status": "queued"})


@router.get("/task/{task_id}", response_model=ApiResponse)
async def get_finetune_task(
    task_id: str, db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)
):
    result = await db.execute(select(FinetuneTask).where(FinetuneTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise ResourceNotFoundException("训练任务不存在")
    return ApiResponse(data=_task_to_view(task))


@router.get("/models", response_model=ApiResponse)
async def list_models(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(RegisteredModel).order_by(RegisteredModel.created_at.desc()).limit(50))
    models = result.scalars().all()
    return ApiResponse(
        data=[
            {
                "modelId": m.id,
                "name": m.name,
                "baseModel": m.base_model,
                "sourceTaskId": m.source_task_id,
                "version": m.version,
                "stage": m.stage,
                "status": m.status,
                "createdAt": str(m.created_at),
            }
            for m in models
        ]
    )


@router.post("/models/register", response_model=ApiResponse)
async def register_model(
    req: RegisterModelRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(require_role("expert", "manager", "admin")),
):
    if req.source_task_id:
        result = await db.execute(select(FinetuneTask).where(FinetuneTask.id == req.source_task_id))
        source_task = result.scalar_one_or_none()
        if source_task is None:
            raise ResourceNotFoundException("来源训练任务不存在")
        if source_task.status != "completed":
            from app.core.exceptions import BusinessException

            raise BusinessException(code=40001, message="只能注册已完成训练的任务产出的模型")

    model_id = f"M{datetime.now().strftime('%Y%m%d')}{uuid4().hex[:4].upper()}"
    model = RegisteredModel(
        id=model_id,
        name=req.name,
        base_model=req.base_model,
        source_task_id=req.source_task_id,
        version=req.version,
        stage=req.stage,
        submitter_id=ctx.user_id,
        status="registered",
    )
    db.add(model)
    await db.commit()
    return ApiResponse(data={"modelId": model_id, "status": "registered"})
