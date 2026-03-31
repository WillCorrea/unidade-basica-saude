import uuid
from django.db import models
from django.conf import settings
from apps.core.models import UBS


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ubs = models.ForeignKey(UBS, on_delete=models.PROTECT, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="audit_logs")

    # Ex.: "invoice.finalized", "dispensation.confirmed", "stock.reversed"
    event = models.CharField(max_length=128)

    # Ex.: "operations.Invoice", "operations.Dispensation", "stock.StockMovement"
    object_type = models.CharField(max_length=128, blank=True, null=True)
    object_id = models.UUIDField(blank=True, null=True)

    # Um id pra correlacionar vários logs numa mesma operação
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False)

    # JSON com detalhes (não guardar dados sensíveis desnecessários)
    payload = models.JSONField(blank=True, null=True)

    # IP e user agent (opcional, mas útil)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=512, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        indexes = [
            models.Index(fields=["ubs", "created_at"]),
            models.Index(fields=["event", "created_at"]),
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["correlation_id"]),
        ]

    def __str__(self):
        return f"{self.created_at} - {self.event}"
