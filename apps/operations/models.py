from django.db import models

# Create your models here.
import uuid
from django.db import models
from django.conf import settings
from apps.core.models import UBS
from apps.catalog.models import Medicine, Batch
from apps.stock.models import StockLocation


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ubs = models.ForeignKey(UBS, on_delete=models.PROTECT, related_name="patients")

    cns = models.CharField(max_length=32)
    cpf = models.CharField(max_length=14, blank=True, null=True)
    full_name = models.CharField(max_length=255)
    mother_name = models.CharField(max_length=255, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)

    address_street = models.CharField(max_length=255, blank=True, null=True)
    address_number = models.CharField(max_length=50, blank=True, null=True)
    address_neighborhood = models.CharField(max_length=255, blank=True, null=True)
    address_city = models.CharField(max_length=255, blank=True, null=True)
    address_state = models.CharField(max_length=2, blank=True, null=True)
    address_zip = models.CharField(max_length=20, blank=True, null=True)
    address_complement = models.CharField(max_length=255, blank=True, null=True)

    is_quick_registration = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "patients"
        indexes = [
            models.Index(fields=["ubs", "full_name"]),
            models.Index(fields=["ubs", "cns"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["ubs", "cns"], name="ux_patients_ubs_cns"),
            models.UniqueConstraint(fields=["ubs", "cpf"], name="ux_patients_ubs_cpf", condition=models.Q(cpf__isnull=False)),
        ]
        permissions = [
            ("view_patient_basic", "Can view patient (basic)"),
            ("view_patient_full", "Can view full patient sensitive data"),
        ]


    def __str__(self):
        return f"{self.full_name} (CNS: {self.cns})"


class Prescription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ubs = models.ForeignKey(UBS, on_delete=models.PROTECT, related_name="prescriptions")
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="prescriptions")

    prescriber_name = models.CharField(max_length=255)
    prescriber_registry_type = models.CharField(max_length=32, blank=True, null=True)   # CRM/COREN/CRO/OUTRO
    prescriber_registry_number = models.CharField(max_length=64, blank=True, null=True)

    origin_unit = models.CharField(max_length=255)  # UBS/UPA/Hospital/etc.
    prescription_type = models.CharField(max_length=64)  # simples por enquanto
    prescription_date = models.DateField()

    attachment_path = models.CharField(max_length=1024, blank=True, null=True)  # foto/pdf opcional

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_prescriptions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "prescriptions"
        indexes = [
            models.Index(fields=["ubs", "prescription_date"]),
            models.Index(fields=["patient", "prescription_date"]),
        ]

    def __str__(self):
        return f"Prescription {self.id} - {self.patient.full_name}"


class Invoice(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_FINALIZED = "FINALIZED"
    STATUS_CANCELED = "CANCELED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ubs = models.ForeignKey(UBS, on_delete=models.PROTECT, related_name="invoices")

    stock_location = models.ForeignKey(
        "stock.StockLocation",
        on_delete=models.PROTECT,
        related_name="invoices",
        null=True,
        blank=True,
    )


    supplier_name = models.CharField(max_length=255)
    invoice_number = models.CharField(max_length=64)
    series = models.CharField(max_length=32, blank=True, null=True)
    access_key = models.CharField(max_length=64, blank=True, null=True)

    issue_date = models.DateField(blank=True, null=True)
    receipt_date = models.DateField()

    status = models.CharField(
        max_length=16,
        choices=[(STATUS_DRAFT, "Draft"), (STATUS_FINALIZED, "Finalized"), (STATUS_CANCELED, "Canceled")],
        default=STATUS_DRAFT,
    )

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_invoices")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoices"
        indexes = [
            models.Index(fields=["ubs", "receipt_date"]),
            models.Index(fields=["ubs", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["ubs", "supplier_name", "invoice_number", "series"], name="ux_invoice_unique"),
        ]
        permissions = [
            ("finalize_invoice", "Can finalize invoice (generate stock entry)"),
            ("cancel_invoice", "Can cancel invoice"),
        ]

    def __str__(self):
        return f"NF {self.invoice_number} - {self.supplier_name} ({self.status})"


class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="items")

    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name="invoice_items", null=True, blank=True)

    lot_number = models.CharField(max_length=64, null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    item_code = models.CharField(max_length=64)   # placeholder (medicine/batch depois)
    item_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=18, decimal_places=3)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invoice_items"
        indexes = [
            models.Index(fields=["invoice"]),
            models.Index(fields=["item_code"]),
        ]

    def __str__(self):
        return f"{self.item_name} x {self.quantity}"



class Dispensation(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_CANCELED = "CANCELED"
    STATUS_REVERSED = "REVERSED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ubs = models.ForeignKey(UBS, on_delete=models.PROTECT, related_name="dispensations")
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="dispensations",verbose_name="Paciente")
    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT, related_name="dispensations")

    stock_location = models.ForeignKey(
        "stock.StockLocation",
        on_delete=models.PROTECT,
        related_name="dispensations",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=16,
        choices=[
            (STATUS_DRAFT, "Draft"),
            (STATUS_CONFIRMED, "Confirmed"),
            (STATUS_CANCELED, "Canceled"),
            (STATUS_REVERSED, "Reversed"),
        ],
        default=STATUS_DRAFT,
    )

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_dispensations")
    created_at = models.DateTimeField("Data de criação", auto_now_add=True)

    class Meta:
        db_table = "dispensations"
        indexes = [
            models.Index(fields=["ubs", "created_at"]),
            models.Index(fields=["patient", "created_at"]),
            models.Index(fields=["ubs", "status"]),
        ]
        permissions = [
            ("confirm_dispensation", "Can confirm dispensation (generate stock out)"),
            ("cancel_dispensation", "Can cancel dispensation"),
        ]

        verbose_name = "Dispensação"
        verbose_name_plural = "Dispensações"        

    def __str__(self):
        return f"Dispensation {self.id} - {self.patient.full_name} ({self.status})"


class DispensationItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    dispensation = models.ForeignKey(Dispensation, on_delete=models.PROTECT, related_name="items")

    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name="dispensation_items", null=True, blank=True)

    # Opcional: se quiser escolher lote manualmente no admin
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="dispensation_items", null=True, blank=True)

    item_code = models.CharField(max_length=64)   # placeholder
    item_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=18, decimal_places=3)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dispensation_items"
        indexes = [
            models.Index(fields=["dispensation"]),
            models.Index(fields=["item_code"]),
        ]

    def __str__(self):
        return f"{self.item_name} x {self.quantity}"


class Inventory(models.Model):
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_PENDING_APPROVAL = "PENDING_APPROVAL"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_COMPLETED = "COMPLETED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ubs = models.ForeignKey(UBS, on_delete=models.PROTECT, related_name="inventories")
    status = models.CharField(
        max_length=32,
        choices=[
            (STATUS_IN_PROGRESS, "In progress"),
            (STATUS_PENDING_APPROVAL, "Pending approval"),
            (STATUS_APPROVED, "Approved"),
            (STATUS_REJECTED, "Rejected"),
            (STATUS_COMPLETED, "Completed"),
        ],
        default=STATUS_IN_PROGRESS,
    )

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_inventories")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="approved_inventories")
    approval_reason = models.TextField(blank=True, null=True)

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventories"
        indexes = [
            models.Index(fields=["ubs", "started_at"]),
            models.Index(fields=["ubs", "status"]),
        ]
        permissions = [
            ("approve_inventory", "Can approve inventory"),
            ("reject_inventory", "Can reject inventory"),
        ]

    def __str__(self):
        return f"Inventory {self.id} ({self.status})"


class InventoryCountItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name="count_items")
    stock_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="inventory_counts")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="inventory_counts")

    counted_quantity = models.DecimalField(max_digits=18, decimal_places=3)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_count_items"
        constraints = [
            models.UniqueConstraint(
                fields=["inventory", "stock_location", "batch"],
                name="ux_inventory_location_batch",
            )
        ]
        indexes = [
            models.Index(fields=["inventory"]),
            models.Index(fields=["stock_location"]),
            models.Index(fields=["batch"]),
        ]

    def __str__(self):
        return f"{self.inventory_id} | {self.stock_location} | {self.batch} => {self.counted_quantity}"
