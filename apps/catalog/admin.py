from django.contrib import admin
from .models import Supplier, Medicine, Batch

from datetime import timedelta
from django.utils import timezone
from django.urls import path
from django.template.response import TemplateResponse

from apps.core.models import UBS
from apps.stock.models import StockLocation, StockBatchBalance


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "cnpj", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("name", "cnpj")


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ("name", "presentation", "anvisa_code", "ean", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("name", "anvisa_code", "ean")


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("medicine", "lot_number", "expiry_date", "ubs", "supplier", "created_at")
    list_filter = ("ubs", "expiry_date")
    search_fields = ("lot_number", "medicine__name", "medicine__presentation")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("reports/expiring-batches/", self.admin_site.admin_view(self.expiring_batches_view), name="expiring-batches"),
        ]
        return custom_urls + urls


    def expiring_batches_view(self, request):
        # filtros
        ubs_id = request.GET.get("ubs_id") or ""
        location_id = request.GET.get("location_id") or ""
        days_raw = request.GET.get("days") or "60"

        try:
            days = int(days_raw)
            if days <= 0:
                days = 60
        except ValueError:
            days = 60

        cutoff = (timezone.now().date() + timedelta(days=days))

        ubs_list = UBS.objects.all().order_by("name")
        location_list = StockLocation.objects.select_related("ubs").all().order_by("ubs__name", "name")

        qs = (
            StockBatchBalance.objects
            .select_related("stock_location__ubs", "batch__medicine")
            .filter(quantity__gt=0, batch__expiry_date__lte=cutoff)
            .order_by("batch__expiry_date", "batch__lot_number")
        )

        if ubs_id:
            qs = qs.filter(stock_location__ubs_id=ubs_id)

        if location_id:
            qs = qs.filter(stock_location_id=location_id)

        rows = []
        for b in qs[:2000]:  # limite para não travar
            rows.append({
                "ubs_name": b.stock_location.ubs.name,
                "location_name": b.stock_location.name,
                "medicine_name": str(b.batch.medicine),
                "lot_number": b.batch.lot_number,
                "expiry_date": b.batch.expiry_date,
                "quantity": b.quantity,
            })

        context = dict(
            self.admin_site.each_context(request),
            ubs_list=ubs_list,
            location_list=location_list,
            rows=rows,
            cutoff_date=cutoff,
            filters={"ubs_id": ubs_id, "location_id": location_id, "days": days},
        )
        return TemplateResponse(request, "admin/catalog/reports/expiring_batches.html", context)
