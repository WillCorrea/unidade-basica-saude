import uuid
from django.db import models
from apps.core.models import UBS


class Supplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, blank=True, null=True)

    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "suppliers"
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["cnpj"]),
        ]

    def __str__(self):
        return self.name


class Medicine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Identificadores comuns (deixa flexível)
    name = models.CharField(max_length=255)                  # "Dipirona Sódica"
    presentation = models.CharField(max_length=255, blank=True, null=True)  # "500mg comprimido"
    anvisa_code = models.CharField(max_length=64, blank=True, null=True)
    ean = models.CharField(max_length=32, blank=True, null=True)

    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "medicines"
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["anvisa_code"]),
            models.Index(fields=["ean"]),
        ]

    def __str__(self):
        if self.presentation:
            return f"{self.name} - {self.presentation}"
        return self.name


class Batch(models.Model):
    """
    Lote por UBS (porque estoque é local).
    FEFO depois: consumir o lote com menor validade.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ubs = models.ForeignKey(UBS, on_delete=models.PROTECT, related_name="batches")
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name="batches")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, blank=True, null=True, related_name="batches")

    lot_number = models.CharField(max_length=64)
    expiry_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "batches"
        indexes = [
            models.Index(fields=["ubs", "medicine"]),
            models.Index(fields=["ubs", "expiry_date"]),
            models.Index(fields=["lot_number"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["ubs", "medicine", "lot_number", "expiry_date"],
                name="ux_batch_ubs_medicine_lot_expiry",
            )
        ]
        permissions = [
            ("manage_catalog", "Can manage catalog (medicine/supplier/batch)"),
        ]

    def __str__(self):
        return f"{self.medicine} | Lote {self.lot_number} | Val {self.expiry_date}"
