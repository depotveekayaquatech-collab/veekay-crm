"""Smart Capping Planner: capacity planning over the Zepto (and Blinkit) stores for a month. Read-only - these routes never write an entry. Needs capping.planner."""
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import capping_planner_export, capping_planner_service

router = APIRouter(prefix="/capping/planner", tags=["capping-planner"])
MAX_LINE = 200


class PlanIn(BaseModel):
    """What to calculate. camelCase (storeLimit); snake_case works too. A blank store limit means every eligible store."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM; this month by default")
    project: Literal["zepto", "blinkit", "all"] = "zepto"
    mode: Literal["max_capacity", "priority_first"] = "priority_first"
    store_limit: StrictInt | None = Field(None, alias="storeLimit", ge=1, le=100_000)
    target: StrictInt = Field(0, ge=0, le=100_000_000, description="the additional count to match")
    priority: list[str] = Field(default_factory=list, description="store names, Outlet IDs or system codes, one per entry, in priority order")

    @field_validator("priority")
    @classmethod
    def _lines(cls, v: list[str]) -> list[str]:
        if any(len(x) > MAX_LINE for x in v):
            raise ValueError(f"Each priority line must be at most {MAX_LINE} characters.")
        return v


def _run(payload: PlanIn, user: User, perms: set[str], db: Session) -> dict:
    return capping_planner_service.run(
        db, user, perms, month_str=payload.month, project=payload.project, mode=payload.mode, store_limit=payload.store_limit, target=payload.target, priority=payload.priority,
    )


@router.post("/plan")
def plan(
    payload: PlanIn,
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """Match the priority list, choose the stores and lay the target over their remaining capacity. A calculation, not an entry: nothing is saved."""
    return _run(payload, user, perms, db)


@router.post("/export")
def export(
    payload: PlanIn,
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> Response:
    """The same calculation as an Excel workbook (configuration, selected stores, all capacities, priority stores, allocation, excluded stores, issues, audit)."""
    result = _run(payload, user, perms, db)
    body = capping_planner_export.build(result, user_name=user.full_name)
    return Response(
        content=body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="smart-capping-plan-{result["month"]}.xlsx"'},
    )
