from fastapi import APIRouter

from app.api.v1.endpoints import (
    activity,
    assignments,
    auth,
    cards,
    compliance,
    employees,
    health,
    orders,
    partners,
    permissions,
    regions,
    stores,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(regions.router)
api_router.include_router(partners.router)
api_router.include_router(stores.router)
api_router.include_router(employees.router)
api_router.include_router(assignments.router)
api_router.include_router(permissions.router)
api_router.include_router(orders.router)
api_router.include_router(activity.router)
api_router.include_router(compliance.router)
api_router.include_router(cards.router)
api_router.include_router(cards.public_router)
