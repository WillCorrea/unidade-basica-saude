from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.contrib.auth.models import Group, Permission
from django.db.models import Q

from .models import UserUbsMembership
from apps.core.models import UBS


@dataclass(frozen=True)
class UbsAuthResult:
    allowed: bool
    reason: str


def has_ubs_perm(*, user, ubs: UBS, perm_codename: str, app_label: Optional[str] = None) -> UbsAuthResult:
    """
    Checks if a user has a permission within the scope of a specific UBS (Design 1).

    Rules:
    1) user must be authenticated and active
    2) user must have an active membership for that UBS
    3) the membership's group must include the requested permission

    perm_codename: ex: "finalize_invoice" or "view_invoice"
    app_label: optional, ex: "operations"
      - if provided, we match permission by (content_type.app_label, codename)
      - if omitted, we match by codename only (OK while MVP)
    """
    if not getattr(user, "is_authenticated", False):
        return UbsAuthResult(False, "user_not_authenticated")

    if not getattr(user, "is_active", False):
        return UbsAuthResult(False, "user_inactive")

    membership_qs = UserUbsMembership.objects.select_related("group").filter(
        user=user,
        ubs=ubs,
        active=True,
        group__isnull=False,
    )

    if not membership_qs.exists():
        return UbsAuthResult(False, "no_active_membership_for_ubs")

    # Collect the groups linked to this UBS for this user
    group_ids = membership_qs.values_list("group_id", flat=True).distinct()

    perm_filter = Q(codename=perm_codename)
    if app_label:
        perm_filter &= Q(content_type__app_label=app_label)

    # Does any of these groups contain the permission?
    allowed = Group.objects.filter(
        id__in=group_ids,
        permissions__in=Permission.objects.filter(perm_filter),
    ).exists()

    if not allowed:
        return UbsAuthResult(False, "permission_denied_for_ubs")

    return UbsAuthResult(True, "ok")
