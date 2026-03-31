import uuid
from apps.audit.services.services import log_event

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.accounts.services import has_ubs_perm
from apps.operations.models import Invoice
from apps.stock.models import StockMovement, StockMovementItem, StockBalance, StockBatchBalance
from apps.catalog.models import Batch, Medicine, Supplier


class InvoiceFinalizeError(Exception):
    pass


@transaction.atomic
def finalize_invoice(*, invoice_id, user, ubs) -> StockMovement:
    """
    Finalizes an Invoice:
    - validates permission in UBS context
    - validates invoice status and required fields
    - creates StockMovement ENTRY + items
    - updates StockBalance
    - marks invoice as FINALIZED
    """
    auth = has_ubs_perm(user=user, ubs=ubs, perm_codename="finalize_invoice", app_label="operations")
    if not auth.allowed:
        raise InvoiceFinalizeError(f"Permission denied: {auth.reason}")

    correlation_id = uuid.uuid4()

    invoice = (
        Invoice.objects
        .select_for_update()
        .select_related("ubs", "stock_location")
        .prefetch_related("items")
        .get(id=invoice_id, ubs=ubs)
    )

    if invoice.status != Invoice.STATUS_DRAFT:
        raise InvoiceFinalizeError(f"Invoice not in DRAFT (current={invoice.status})")

    if invoice.stock_location is None:
        raise InvoiceFinalizeError("Invoice missing stock_location")

    items = list(invoice.items.all())
    if not items:
        raise InvoiceFinalizeError("Invoice has no items")

    # Create stock movement
    movement = StockMovement.objects.create(
        ubs=ubs,
        movement_type=StockMovement.TYPE_ENTRY,
        status=StockMovement.STATUS_CONFIRMED,
        stock_location_to=invoice.stock_location,
        reference_type="INVOICE",
        reference_id=invoice.id,
        note=f"Entrada por NF {invoice.invoice_number} ({invoice.supplier_name})",
        created_by=user,
    )

    # Create movement items and update balances
    for it in items:
        qty = Decimal(it.quantity)
        if qty <= 0:
            raise InvoiceFinalizeError(f"Invalid quantity for item {it.item_code}: {it.quantity}")

        if it.medicine_id is None or not it.lot_number or not it.expiry_date:
            raise InvoiceFinalizeError("InvoiceItem precisa de medicine + lot_number + expiry_date para estoque por lote")

        # 1) cria/pega batch SEMPRE antes de usar
        batch, _ = Batch.objects.get_or_create(
            ubs=ubs,
            medicine_id=it.medicine_id,
            lot_number=it.lot_number,
            expiry_date=it.expiry_date,
            defaults={"supplier": None},
        )

        # 2) atualiza saldo por lote
        bb, _ = StockBatchBalance.objects.select_for_update().get_or_create(
            stock_location=invoice.stock_location,
            batch=batch,
            defaults={"quantity": Decimal("0")},
        )
        bb.quantity = (bb.quantity or Decimal("0")) + qty
        bb.updated_at = timezone.now()
        bb.save()

        # 3) grava movimento com lote
        StockMovementItem.objects.create(
            movement=movement,
            batch=batch,
            item_code=str(it.medicine_id),   # legado: medicine_id como código
            item_name=it.item_name,
            quantity=qty,
        )


    # Mark invoice finalized
    invoice.status = Invoice.STATUS_FINALIZED
    invoice.updated_at = timezone.now()
    invoice.save(update_fields=["status", "updated_at"])

    log_event(
        ubs=ubs,
        actor=user,
        event="invoice.finalized",
        object_type="operations.Invoice",
        object_id=invoice.id,
        correlation_id=correlation_id,
        payload={
            "invoice_number": invoice.invoice_number,
            "supplier_name": invoice.supplier_name,
            "stock_location_id": str(invoice.stock_location_id),
            "movement_id": str(movement.id),
            "items_count": len(items),
        },
    )

    return movement
