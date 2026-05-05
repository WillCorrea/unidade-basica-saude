from decimal import Decimal
import uuid
from django.db import transaction
from django.utils import timezone

from apps.operations.models import Order, OrderItem, OrderReceiveItem
from apps.stock.models import StockMovement, StockMovementItem, StockBatchBalance, StockLocation
from apps.catalog.models import Batch

class OrderReceiveError(Exception):
    pass


@transaction.atomic
def receive_order(*, order_id, user, ubs):
    order = (
        Order.objects
        .select_for_update()
        .prefetch_related("items")
        .get(id=order_id, ubs=ubs)
    )

    if order.status not in [Order.STATUS_SUBMITTED, Order.STATUS_PARTIALLY_RECEIVED]:
        raise Exception("Order not ready to receive")

    stock_location = order.stock_location
    if not stock_location:
        stock_location = StockLocation.objects.filter(ubs=ubs, active=True).first()
        if not stock_location:
            raise OrderReceiveError("Nenhum local de estoque disponível para este pedido")

    movement = StockMovement.objects.create(
        ubs=ubs,
        movement_type=StockMovement.TYPE_ENTRY,
        status=StockMovement.STATUS_CONFIRMED,
        stock_location_to=stock_location,
        reference_type="ORDER",
        reference_id=order.id,
        created_by=user,
    )

    for item in order.items.all():
        qty_to_receive = item.quantity_requested - item.quantity_received
        if qty_to_receive <= 0:
            continue

        # cria lote (simples por enquanto)
        batch = Batch.objects.create(
            ubs=ubs,
            medicine=item.medicine,
            lot_number=str(uuid.uuid4())[:8],
            expiry_date=timezone.now().date(),
        )

        StockBatchBalance.objects.create(
            stock_location=stock_location,
            batch=batch,
            quantity=qty_to_receive,
        )

        StockMovementItem.objects.create(
            movement=movement,
            batch=batch,
            quantity=qty_to_receive,
        )

        # item.quantity_received += qty_to_receive  # Removido: agora é calculado dinamicamente
        # item.save()  # Removido: não há mais campo para salvar

    order.status = Order.STATUS_RECEIVED
    order.received_at = timezone.now()
    order.save()

    return movement


def receive_order_partial(*, order_id, user, ubs, items_data: list):
    """
    items_data = [
        {
            "order_item_id": UUID,
            "quantity": Decimal,
            "lot_number": str,
            "expiry_date": date,
        }
    ]
    """

    order = (
        Order.objects
        .select_for_update()
        .prefetch_related("items")
        .get(id=order_id, ubs=ubs)
    )

    if order.status not in [Order.STATUS_SUBMITTED, Order.STATUS_PARTIALLY_RECEIVED]:
        raise OrderReceiveError("Pedido não está pronto para recebimento")

    stock_location = order.stock_location
    if not stock_location:
        stock_location = StockLocation.objects.filter(ubs=ubs, active=True).first()
        if not stock_location:
            raise OrderReceiveError("Nenhum local de estoque disponível para este pedido")

    movement = StockMovement.objects.create(
        ubs=ubs,
        movement_type=StockMovement.TYPE_ENTRY,
        status=StockMovement.STATUS_CONFIRMED,
        stock_location_to=stock_location,
        reference_type="ORDER",
        reference_id=order.id,
        created_by=user,
    )

    any_received = False

    for data in items_data:
        order_item = OrderItem.objects.select_for_update().get(id=data["order_item_id"])

        qty = Decimal(data["quantity"])
        if qty <= 0:
            raise OrderReceiveError("Quantidade inválida")

        remaining = order_item.quantity_requested - order_item.quantity_received

        if qty > remaining:
            raise OrderReceiveError("Quantidade maior que o restante do pedido")

        # cria lote
        batch = Batch.objects.create(
            ubs=ubs,
            medicine=order_item.medicine,
            lot_number=data["lot_number"],
            expiry_date=data["expiry_date"],
        )

        # atualiza estoque
        bb, _ = StockBatchBalance.objects.select_for_update().get_or_create(
            stock_location=stock_location,
            batch=batch,
            defaults={"quantity": Decimal("0")},
        )

        bb.quantity += qty
        bb.save()

        # movimento
        StockMovementItem.objects.create(
            movement=movement,
            batch=batch,
            item_code=str(order_item.medicine_id),
            item_name=str(order_item.medicine),
            quantity=qty,
        )

        # controle de recebimento
        OrderReceiveItem.objects.create(
            order=order,
            order_item=order_item,
            batch=batch,
            quantity=qty,
            created_by=user,
        )

        # order_item.quantity_received += qty  # Removido: agora é calculado dinamicamente
        # order_item.save()  # Removido: não há mais campo para salvar

        any_received = True

    if not any_received:
        raise OrderReceiveError("Nenhum item foi recebido")

    # 🔥 Atualiza status automaticamente
    all_done = all(
        i.quantity_received >= i.quantity_requested
        for i in order.items.all()
    )

    if all_done:
        order.status = Order.STATUS_RECEIVED
        order.received_at = timezone.now()
    else:
        order.status = Order.STATUS_PARTIALLY_RECEIVED

    order.save()

    return movement