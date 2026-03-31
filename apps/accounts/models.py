import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from apps.core.models import UBS


class User(AbstractUser):
    """
    Custom user with UUID primary key.
    Keeps Django auth features (groups, permissions, is_staff, etc.)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Se quiser, depois podemos adicionar campos extras aqui (telefone, cpf do servidor, etc.)
    # phone = models.CharField(max_length=30, blank=True, null=True)

    class Meta:
        db_table = "users"


class UserUbsMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ubs_memberships")
    ubs = models.ForeignKey(UBS, on_delete=models.PROTECT, related_name="memberships")
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="ubs_memberships")

    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_ubs_memberships"
        unique_together = ("user", "ubs", "group")
        indexes = [
            models.Index(fields=["user", "active"]),
            models.Index(fields=["ubs", "active"]),
            models.Index(fields=["group"]),
        ]

    def __str__(self):
        status = "active" if self.active else "inactive"
        return f"{self.user.username} @ {self.ubs.name} ({self.group.name}) [{status}]"