import uuid
from django.db import models
from django.conf import settings
from apps.core.models import UBS
from apps.catalog.models import Batch


class StockLocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ubs = models.ForeignKey(UBS, on_delete=models.PROTECT, related_name="stock_locations")
    name = models.CharField(max_length=255)
    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stock_locations"
        unique_together = ("ubs", "name")
        indexes = [
            models.Index(fields=["ubs", "active"]),
            models.Index(fields=["ubs", "name"]),
        ]

    def __str__(self):
        return f"{self.ubs.name} - {self.name}"


class StockBalance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    stock_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="balances")

    item_code = models.CharField(max_length=64)     # placeholder
    item_name = models.CharField(max_length=255)    # placeholder
    quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stock_balances"
        unique_together = ("stock_location", "item_code")
        indexes = [
            models.Index(fields=["stock_location"]),
            models.Index(fields=["item_code"]),
        ]
        permissions = [
            ("view_stock_statement", "Can view stock statement (movements/extract)"),
        ]

    def __str__(self):
        return f"{self.stock_location} - {self.item_name}: {self.quantity}"



class StockBatchBalance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    stock_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="batch_balances")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="balances")

    quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stock_batch_balances"
        constraints = [
            models.UniqueConstraint(fields=["stock_location", "batch"], name="ux_balance_location_batch")
        ]
        indexes = [
            models.Index(fields=["stock_location"]),
            models.Index(fields=["batch"]),
        ]

    def __str__(self):
        return f"{self.stock_location} | {self.batch} => {self.quantity}"



class StockMovement(models.Model):
    TYPE_ENTRY = "ENTRY"
    TYPE_OUT = "OUT"
    TYPE_TRANSFER = "TRANSFER"
    TYPE_ADJUST = "ADJUST"
    TYPE_REVERSAL = "REVERSAL"

    STATUS_DRAFT = "DRAFT"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_CANCELED = "CANCELED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ubs = models.ForeignKey(UBS, on_delete=models.PROTECT, related_name="stock_movements")

    movement_type = models.CharField(
        max_length=16,
        choices=[
            (TYPE_ENTRY, "Entry"),
            (TYPE_OUT, "Out"),
            (TYPE_TRANSFER, "Transfer"),
            (TYPE_ADJUST, "Adjust"),
            (TYPE_REVERSAL, "Reversal"),
        ],
    )

    status = models.CharField(
        max_length=16,
        choices=[(STATUS_DRAFT, "Draft"), (STATUS_CONFIRMED, "Confirmed"), (STATUS_CANCELED, "Canceled")],
        default=STATUS_DRAFT,
    )

    stock_location_from = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, blank=True, null=True, related_name="movements_from"
    )
    stock_location_to = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, blank=True, null=True, related_name="movements_to"
    )

    reference_type = models.CharField(max_length=64, blank=True, null=True)
    reference_id = models.UUIDField(blank=True, null=True)

    note = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_stock_movements")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movements"
        indexes = [
            models.Index(fields=["ubs", "created_at"]),
            models.Index(fields=["ubs", "movement_type"]),
            models.Index(fields=["ubs", "status"]),
        ]
        permissions = [
            ("transfer_stock", "Can transfer stock between locations"),
            ("adjust_stock_request", "Can request stock adjustment"),
            ("adjust_stock_approve", "Can approve stock adjustment"),
            ("reverse_stock_movement", "Can reverse/undo a stock movement"),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.id} ({self.status})"


class StockMovementItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    movement = models.ForeignKey(StockMovement, on_delete=models.PROTECT, related_name="items")

    batch = models.ForeignKey(
        Batch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movement_items",
    )

    item_code = models.CharField(max_length=64)
    item_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=18, decimal_places=3)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movement_items"
        indexes = [
            models.Index(fields=["movement"]),
            models.Index(fields=["item_code"]),
        ]

    def __str__(self):
        return f"{self.item_name} x {self.quantity}"


class MovementReversal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    original_movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="reversal")
    reversal_movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="reversal_of")

    reason = models.TextField()

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_reversals")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "movement_reversals"
        indexes = [
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Reversal {self.id}"
