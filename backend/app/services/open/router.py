from fastapi import APIRouter, Query
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/open", tags=["开放接口"])


@router.get("/failure-modes", response_model=ApiResponse)
async def get_failure_modes(component: str = Query(None), domain: str = Query(None)):
    return ApiResponse(data=[])


@router.get("/diagnosis-rules", response_model=ApiResponse)
async def get_diagnosis_rules(symptom: str = Query(None)):
    return ApiResponse(data=[])


@router.post("/similar-cases", response_model=ApiResponse)
async def search_similar_cases(req: dict):
    return ApiResponse(data=[])


@router.post("/feedback-case", response_model=ApiResponse)
async def feedback_case(req: dict):
    return ApiResponse(data={"status": "accepted"})