from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event", "ubs", "actor", "object_type", "object_id")
    list_filter = ("event", "ubs")
    search_fields = ("event", "object_type", "object_id", "actor__username")
    readonly_fields = ("id", "created_at")

    ordering = ("-created_at",)
