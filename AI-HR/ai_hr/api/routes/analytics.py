from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.analytics import DashboardAnalyticsResult, HiringCenterOverviewResult
from ...services.analytics import get_analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/dashboard", response_model=Envelope[DashboardAnalyticsResult])
def get_dashboard_analytics(
    session: Session = Depends(get_db_session)
) -> Envelope[DashboardAnalyticsResult]:
    """获取仪表盘实时统计数据。"""
    service = get_analytics_service(session)
    result = service.get_dashboard_summary()
    return Envelope.success(result)


@router.get("/hiring-center", response_model=Envelope[HiringCenterOverviewResult])
def get_hiring_center_overview(
    top_n: int = 3,
    queue_limit: int = 20,
    max_scan: int = 3000,
    session: Session = Depends(get_db_session),
) -> Envelope[HiringCenterOverviewResult]:
    """Get hiring center aggregated data in one request."""
    service = get_analytics_service(session)
    result = service.get_hiring_center_overview(top_n=top_n, queue_limit=queue_limit, max_scan=max_scan)
    return Envelope.success(result)
