import uuid
from apps.audit.services.services import log_event

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.accounts.services import has_ubs_perm
from apps.operations.models import Dispensation
from apps.stock.models import StockMovement, StockMovementItem, StockBalance, StockBatchBalance
from apps.catalog.models import Batch  # se ainda não tiver no topo

class DispensationConfirmError(Exception):
    pass


@transaction.atomic
def confirm_dispensation(*, dispensation_id, user, ubs) -> StockMovement:
    auth = has_ubs_perm(user=user, ubs=ubs, perm_codename="confirm_dispensation", app_label="operations")
    if not auth.allowed:
        raise DispensationConfirmError(f"Permission denied: {auth.reason}")

    correlation_id = uuid.uuid4()

    disp = (
        Dispensation.objects
        .select_for_update()
        .select_related("ubs", "stock_location", "patient")
        .prefetch_related("items")  # pode manter simples
        .get(id=dispensation_id, ubs=ubs)
    )


    if disp.status != Dispensation.STATUS_DRAFT:
        raise DispensationConfirmError(f"Dispensation not in DRAFT (current={disp.status})")

    if disp.stock_location is None:
        raise DispensationConfirmError("Dispensation missing stock_location")

    items = list(disp.items.all())
    if not items:
        raise DispensationConfirmError("Dispensation has no items")

    movement = StockMovement.objects.create(
        ubs=ubs,
        movement_type=StockMovement.TYPE_OUT,
        status=StockMovement.STATUS_CONFIRMED,
        stock_location_from=disp.stock_location,
        reference_type="DISPENSATION",
        reference_id=disp.id,
        note=f"Saída por dispensação {disp.id} (Paciente: {disp.patient.full_name})",
        created_by=user,
    )

    for it in items:
        qty = Decimal(it.quantity)
        if qty <= 0:
            raise DispensationConfirmError(f"Quantidade inválida para o item: {it.item_code}: {it.quantity}")

        if it.medicine_id is None:
            raise DispensationConfirmError("DispensationItem precisa de medicine para FEFO")

        remaining = qty
        # today = timezone.now().date()
        today = timezone.localdate()

        # --- Escolha manual de lote ---
        if it.batch_id:
            # Busca o lote SEM depender de prefetch
            batch = Batch.objects.filter(id=it.batch_id, ubs=ubs).first()
            if not batch:
                raise DispensationConfirmError("Lote inválido para esta UBS")

            if batch.expiry_date < today:
                raise DispensationConfirmError(
                    f"Lote vencido: {batch.lot_number} (validade={batch.expiry_date})"
                )

            balances = list(
                StockBatchBalance.objects.select_for_update().filter(
                    stock_location=disp.stock_location,
                    batch=batch,
                    quantity__gt=0,
                ).select_related("batch", "batch__medicine")
            )

        else:
            # --- FEFO automático: filtra NÃO vencidos ---
            balances = list(
                StockBatchBalance.objects.select_for_update().filter(
                    stock_location=disp.stock_location,
                    batch__medicine_id=it.medicine_id,
                    quantity__gt=0,
                    batch__expiry_date__gte=today,  # <<< BLOQUEIO AQUI
                ).select_related("batch", "batch__medicine").order_by(
                    "batch__expiry_date", "batch__lot_number"
                )
            )

        total_available = sum([b.quantity for b in balances], Decimal("0"))
        if total_available < remaining:
            # Se quiser uma mensagem mais clara quando só tem vencido:
            has_any = StockBatchBalance.objects.filter(
                stock_location=disp.stock_location,
                batch__medicine_id=it.medicine_id,
                quantity__gt=0,
            ).exists()
            if has_any and not balances:
                raise DispensationConfirmError("Só há lotes vencidos disponíveis para este medicamento.")
            raise DispensationConfirmError(
                f"Saldo insuficiente (medicine_id={it.medicine_id}) available={total_available} requested={remaining}"
            )

        # Consumir em cascata (FEFO) ou do lote manual
        for b in balances:
            if remaining <= 0:
                break

            take = min(b.quantity, remaining)
            b.quantity = b.quantity - take
            b.updated_at = timezone.now()
            b.save()

            # grava o movimento por lote consumido
            StockMovementItem.objects.create(
                movement=movement,
                batch=b.batch,
                item_code=str(it.medicine_id),
                item_name=str(b.batch.medicine),
                quantity=take,
            )

            remaining -= take

    disp.status = Dispensation.STATUS_CONFIRMED
    disp.save(update_fields=["status"])

    log_event(
        ubs=ubs,
        actor=user,
        event="dispensation.confirmed",
        object_type="operations.Dispensation",
        object_id=disp.id,
        correlation_id=correlation_id,
        payload={
            "patient_id": str(disp.patient_id),
            "prescription_id": str(disp.prescription_id),
            "stock_location_id": str(disp.stock_location_id),
            "movement_id": str(movement.id),
            "items_count": len(items),
        },
    )

    return movement
