from django.contrib import admin
from .models import UBS


@admin.register(UBS)
class UBSAdmin(admin.ModelAdmin):
    list_display = ("name", "cnes", "active", "address_city", "address_state", "updated_at")
    list_filter = ("active", "address_state")
    search_fields = ("name", "cnes", "address_city")
