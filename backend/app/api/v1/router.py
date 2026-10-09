from fastapi import APIRouter

from app.api.v1.endpoints import (
    activity,
    assignments,
    attendance,
    auth,
    bottles,
    cards,
    cash_adjustments,
    cash_purchases,
    external_accounts,
    compliance,
    employees,
    health,
    integrations,
    orders,
    partner,
    partners,
    permissions,
    regions,
    stores,
    test_reports,
    tickets,
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
api_router.include_router(attendance.router)
api_router.include_router(tickets.router)
api_router.include_router(partner.router)
api_router.include_router(integrations.router)
api_router.include_router(test_reports.router)
api_router.include_router(cash_purchases.router)
api_router.include_router(cash_adjustments.router)
api_router.include_router(bottles.router)
api_router.include_router(external_accounts.router)
