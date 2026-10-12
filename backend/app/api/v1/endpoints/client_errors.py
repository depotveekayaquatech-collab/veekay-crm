"""App crash / error reports from the mobile app. Public on purpose (a crash can happen before anyone is signed in), so it
is small, rate limited like the other public routes (/public/*), writes nothing to the database, and logs one line that
your log tool can alert on."""
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/public", tags=["public"])
log = logging.getLogger("veekay.client_errors")


class ClientError(BaseModel):
    app: str = Field(default="mobile", max_length=32)
    version: str = Field(default="", max_length=32)
    platform: str = Field(default="", max_length=64)
    screen: str = Field(default="", max_length=120)
    message: str = Field(..., max_length=500)
    stack: str = Field(default="", max_length=4000)
    fatal: bool = False


@router.post("/client-errors", status_code=204)
def report(body: ClientError) -> None:
    log.error(
        "client error [%s %s %s] %s%s | screen=%s",
        body.app, body.version, body.platform, "FATAL " if body.fatal else "", body.message.replace("\n", " "), body.screen,
        extra={"stack": body.stack},
    )
