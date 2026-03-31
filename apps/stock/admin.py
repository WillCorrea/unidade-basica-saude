from django.contrib import admin
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import path
from django.utils.html import format_html
from apps.stock.services.reversal_service import reverse_stock_movement, StockReversalError
from .models import StockLocation, StockBalance, StockMovement, StockMovementItem, MovementReversal
from django.template.response import TemplateResponse
from .models import StockBatchBalance



@admin.register(StockLocation)
class StockLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "ubs", "active", "updated_at")
    list_filter = ("ubs", "active")
    search_fields = ("name",)


@admin.register(StockBalance)
class StockBalanceAdmin(admin.ModelAdmin):
    list_display = ("stock_location", "item_code", "item_name", "quantity", "updated_at")
    list_filter = ("stock_location__ubs", "stock_location")
    search_fields = ("item_code", "item_name")


class StockMovementItemInline(admin.TabularInline):
    model = StockMovementItem
    extra = 0


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("movement_type", "status", "ubs", "stock_location_from", "stock_location_to", "reverse_button", "created_at")
    list_filter = ("ubs", "movement_type", "status")
    search_fields = ("id", "reference_type")
    inlines = [StockMovementItemInline]

    def reverse_button(self, obj):
        if obj.status == obj.STATUS_CONFIRMED and not hasattr(obj, "reversal"):
            return format_html('<a class="button" href="{}">Estornar</a>', f"{obj.id}/reverse/")
        return "-"
        reverse_button.short_description = "Ação"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("<uuid:movement_id>/reverse/", self.admin_site.admin_view(self.reverse_view), name="stockmovement-reverse"),
        ]
        return custom_urls + urls

    def reverse_view(self, request, movement_id):
        movement = StockMovement.objects.select_related("ubs").filter(id=movement_id).first()
        if not movement:
            self.message_user(request, "Movimento não encontrado.", level=messages.ERROR)
            return redirect("../..")

        # GET: renderiza tela de confirmação
        if request.method == "GET":
            context = dict(
                self.admin_site.each_context(request),
                movement=movement,
            )
            return TemplateResponse(request, "admin/stock/stockmovement/reverse_form.html", context)

        # POST: processa estorno
        reason = request.POST.get("reason")
        if not reason:
            self.message_user(request, "Motivo do estorno é obrigatório.", level=messages.ERROR)
            return redirect(request.path)

        try:
            reverse_stock_movement(
                movement_id=movement.id,
                user=request.user,
                ubs=movement.ubs,
                reason=reason,
            )
            self.message_user(request, "Movimento estornado com sucesso.", level=messages.SUCCESS)
        except StockReversalError as e:
            self.message_user(request, f"Falha ao estornar: {e}", level=messages.ERROR)

        return redirect("../..")


@admin.register(StockBatchBalance)
class StockBatchBalanceAdmin(admin.ModelAdmin):
    list_display = ("stock_location", "batch", "quantity", "updated_at")
    list_filter = ("stock_location__ubs", "stock_location", "batch__expiry_date")
    search_fields = ("batch__lot_number", "batch__medicine__name", "batch__medicine__presentation")


@admin.register(MovementReversal)
class MovementReversalAdmin(admin.ModelAdmin):
    list_display = ("original_movement", "reversal_movement", "created_by", "created_at")
    search_fields = ("original_movement__id", "reversal_movement__id")
