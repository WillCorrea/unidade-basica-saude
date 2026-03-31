from decimal import Decimal
from apps.audit.services.services import log_event

from django.db import transaction
from django.utils import timezone

from apps.accounts.services import has_ubs_perm
from apps.stock.models import StockMovement, StockMovementItem, StockBalance, MovementReversal, StockBatchBalance


class StockReversalError(Exception):
    pass


@transaction.atomic
def reverse_stock_movement(*, movement_id, user, ubs, reason: str) -> StockMovement:
    """
    Reverses a confirmed StockMovement:
    - validates permission
    - validates original movement status
    - prevents double reversal
    - creates inverse StockMovement
    - updates StockBalance
    - links via MovementReversal
    """
    auth = has_ubs_perm(user=user, ubs=ubs, perm_codename="reverse_stock_movement", app_label="stock")
    if not auth.allowed:
        raise StockReversalError(f"Permission denied: {auth.reason}")

    original = (
        StockMovement.objects
        .select_for_update()
        .prefetch_related("items")
        .get(id=movement_id, ubs=ubs)
    )

    if original.status != StockMovement.STATUS_CONFIRMED:
        raise StockReversalError(f"Only CONFIRMED movements can be reversed (current={original.status})")

    if hasattr(original, "reversal"):
        raise StockReversalError("This movement has already been reversed")

    # Determine inverse movement type
    if original.movement_type == StockMovement.TYPE_ENTRY:
        inverse_type = StockMovement.TYPE_REVERSAL
        stock_location_from = original.stock_location_to
        stock_location_to = None
        sign = Decimal("-1")
    elif original.movement_type == StockMovement.TYPE_OUT:
        if original.stock_location_from is None:
            raise StockReversalError("Cannot reverse OUT movement without stock_location_from")

        inverse_type = StockMovement.TYPE_REVERSAL
        stock_location_from = None
        stock_location_to = original.stock_location_from  # devolve pro mesmo local de onde saiu
        sign = Decimal("1")
    else:
        raise StockReversalError(f"Reversal not supported for movement type {original.movement_type}")

    # Create reversal movement
    reversal_movement = StockMovement.objects.create(
        ubs=ubs,
        movement_type=inverse_type,
        status=StockMovement.STATUS_CONFIRMED,
        stock_location_from=stock_location_from,
        stock_location_to=stock_location_to,
        reference_type="REVERSAL",
        reference_id=original.id,
        note=f"Estorno de movimento {original.id}. Motivo: {reason}",
        created_by=user,
    )

    # Process each item
    for it in original.items.all():
        if it.batch_id is None:
            raise StockReversalError("Cannot reverse movement item without batch (missing lot trace)")

        qty = Decimal(it.quantity) * sign

        StockMovementItem.objects.create(
            movement=reversal_movement,
            # item_code=it.item_code,
            item_code=it.batch,
            item_name=it.item_name,
            quantity=abs(qty),
        )

        # ENTRY reversal: subtract from the same lot in the same location
        if stock_location_from:
            bb = StockBatchBalance.objects.select_for_update().filter(
                stock_location=stock_location_from,
                batch_id=it.batch_id,
            ).first()

            if not bb or bb.quantity < it.quantity:
                raise StockReversalError(f"Insufficient stock to reverse batch {it.batch_id}")

            bb.quantity = bb.quantity - it.quantity
            bb.updated_at = timezone.now()
            bb.save()

        # OUT reversal: add back to the same lot in the same location
        else:
            bb, _ = StockBatchBalance.objects.select_for_update().get_or_create(
                stock_location=stock_location_to,
                batch_id=it.batch_id,
                defaults={"quantity": Decimal("0")},
            )
            bb.quantity = bb.quantity + it.quantity
            bb.updated_at = timezone.now()
            bb.save()


        # # Update balance
        # if stock_location_from:
        #     # ENTRY reversal: subtract from location
        #     balance = StockBalance.objects.select_for_update().filter(
        #         stock_location=stock_location_from,
        #         item_code=it.item_code,
        #     ).first()
        #     if not balance or balance.quantity < abs(qty):
        #         raise StockReversalError(
        #             f"Insufficient stock to reverse item {it.item_code}"
        #         )
        #     balance.quantity = balance.quantity + qty  # qty is negative
        # else:
        #     # OUT reversal: add back to location
        #     balance = StockBalance.objects.select_for_update().get_or_create(
        #         stock_location=stock_location_to,
        #         item_code=it.item_code,
        #         defaults={"item_name": it.item_name, "quantity": Decimal("0")},
        #     )[0]
        #     balance.quantity = balance.quantity + abs(qty)

        # balance.updated_at = timezone.now()
        # balance.save()

    # Link reversal
    MovementReversal.objects.create(
        original_movement=original,
        reversal_movement=reversal_movement,
        reason=reason,
        created_by=user,
    )

    # Cancel original
    original.status = StockMovement.STATUS_CANCELED
    original.save(update_fields=["status"])


    log_event(
        ubs=ubs,
        actor=user,
        event="stock.reversed",
        object_type="stock.StockMovement",
        object_id=original.id,
        payload={
            "original_movement_id": str(original.id),
            "reversal_movement_id": str(reversal_movement.id),
            "original_type": original.movement_type,
            "reason": reason,
        },
    )

    return reversal_movement
