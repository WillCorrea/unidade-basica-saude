import uuid
from django.db import models


class UBS(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255)
    cnes = models.CharField(max_length=32, blank=True, null=True)
    active = models.BooleanField(default=True)

    # Endereço (como combinamos)
    address_street = models.CharField(max_length=255, blank=True, null=True)
    address_number = models.CharField(max_length=50, blank=True, null=True)
    address_neighborhood = models.CharField(max_length=255, blank=True, null=True)
    address_city = models.CharField(max_length=255, blank=True, null=True)
    address_state = models.CharField(max_length=2, blank=True, null=True)
    address_zip = models.CharField(max_length=20, blank=True, null=True)
    address_complement = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ubs"
        indexes = [
            models.Index(fields=["active"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.name}"
