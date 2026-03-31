from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounts.services import has_ubs_perm
from apps.audit.services.services import log_event
from apps.operations.models import Inventory
from apps.stock.models import StockMovement, StockMovementItem, StockBatchBalance


class InventoryApproveError(Exception):
    pass

class InventorySubmitError(Exception):
    pass


@transaction.atomic
def submit_inventory(*, inventory_id, user, ubs, note: str = "") -> Inventory:
    """
    Submits an inventory for approval (PENDING_APPROVAL).
    Does NOT change stock. Only locks the inventory workflow.
    """
    auth = has_ubs_perm(user=user, ubs=ubs, perm_codename="adjust_stock_request", app_label="stock")
    if not auth.allowed:
        # se preferir, pode criar perm específica no operations depois
        raise InventorySubmitError(f"Permission denied: {auth.reason}")

    inv = (
        Inventory.objects
        .select_for_update()
        .select_related("ubs")
        .prefetch_related("count_items")
        .get(id=inventory_id, ubs=ubs)
    )

    if inv.status != Inventory.STATUS_IN_PROGRESS:
        raise InventorySubmitError(f"Inventory must be IN_PROGRESS to submit (current={inv.status})")

    if not inv.count_items.exists():
        raise InventorySubmitError("Inventory has no count items")

    inv.status = Inventory.STATUS_PENDING_APPROVAL
    inv.updated_at = timezone.now()
    inv.save(update_fields=["status", "updated_at"])

    log_event(
        ubs=ubs,
        actor=user,
        event="inventory.submitted",
        object_type="operations.Inventory",
        object_id=inv.id,
        payload={"note": note},
    )

    return inv


@transaction.atomic
def approve_inventory(*, inventory_id, user, ubs, reason: str = "") -> StockMovement:
    auth = has_ubs_perm(user=user, ubs=ubs, perm_codename="approve_inventory", app_label="operations")
    if not auth.allowed:
        raise InventoryApproveError(f"Permission denied: {auth.reason}")

    inv = (
        Inventory.objects
        .select_for_update()
        .select_related("ubs")
        .prefetch_related("count_items__stock_location", "count_items__batch", "count_items__batch__medicine")
        .get(id=inventory_id, ubs=ubs)
    )

    if inv.status not in [Inventory.STATUS_IN_PROGRESS, Inventory.STATUS_PENDING_APPROVAL]:
        raise InventoryApproveError(f"Inventory status invalid for approval: {inv.status}")

    count_items = list(inv.count_items.all())
    if not count_items:
        raise InventoryApproveError("Inventory has no count items")

    # Criar movimento de ajuste (um único movimento por inventário)
    movement = StockMovement.objects.create(
        ubs=ubs,
        movement_type=StockMovement.TYPE_ADJUST,
        status=StockMovement.STATUS_CONFIRMED,
        reference_type="INVENTORY",
        reference_id=inv.id,
        note=f"Ajuste por Inventário {inv.id}. {reason}".strip(),
        created_by=user,
    )

    adjustments_applied = 0

    for ci in count_items:
        # saldo atual do lote naquele local
        bb, _ = StockBatchBalance.objects.select_for_update().get_or_create(
            stock_location=ci.stock_location,
            batch=ci.batch,
            defaults={"quantity": Decimal("0")},
        )

        current_qty = bb.quantity or Decimal("0")
        counted_qty = Decimal(ci.counted_quantity)

        diff = counted_qty - current_qty  # >0 precisa aumentar, <0 precisa reduzir
        if diff == 0:
            continue

        # Atualiza saldo para o valor contado (ajuste)
        bb.quantity = counted_qty
        bb.updated_at = timezone.now()
        bb.save()

        # Registra item do movimento com lote (quantidade absoluta)
        StockMovementItem.objects.create(
            movement=movement,
            batch=ci.batch,
            item_code=str(ci.batch.medicine_id),  # legado
            item_name=str(ci.batch.medicine),
            quantity=abs(diff),
        )

        adjustments_applied += 1

    inv.status = Inventory.STATUS_APPROVED
    inv.approved_by = user
    inv.approval_reason = reason
    inv.finished_at = timezone.now()
    inv.updated_at = timezone.now()
    inv.save(update_fields=["status", "approved_by", "approval_reason", "finished_at", "updated_at"])

    log_event(
        ubs=ubs,
        actor=user,
        event="inventory.approved",
        object_type="operations.Inventory",
        object_id=inv.id,
        payload={
            "movement_id": str(movement.id),
            "adjustments_applied": adjustments_applied,
            "reason": reason,
        },
    )

    return movement
