from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from django.http import HttpRequest

from apps.audit.models import AuditLog


def log_event(
    *,
    ubs,
    actor,
    event: str,
    object_type: Optional[str] = None,
    object_id: Optional[UUID] = None,
    payload: Optional[Dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
    correlation_id: Optional[UUID] = None,
) -> AuditLog:
    ip = None
    ua = None

    if request is not None:
        ip = request.META.get("REMOTE_ADDR")
        ua = request.META.get("HTTP_USER_AGENT")

    kwargs = {}
    if correlation_id is not None:
        kwargs["correlation_id"] = correlation_id

    return AuditLog.objects.create(
        ubs=ubs,
        actor=actor,
        event=event,
        object_type=object_type,
        object_id=object_id,
        payload=payload,
        ip_address=ip,
        user_agent=ua,
        **kwargs,
    )
