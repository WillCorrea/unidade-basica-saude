from django.contrib import admin
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import path
from django.utils.html import format_html
from apps.operations.services.invoice_service import finalize_invoice, InvoiceFinalizeError
from apps.core.models import UBS
from .models import Patient, Prescription, Invoice, InvoiceItem, Dispensation, DispensationItem, Inventory
from apps.operations.services.dispensation_service import confirm_dispensation, DispensationConfirmError

from apps.audit.services.services import log_event
from apps.accounts.services import has_ubs_perm

from .models import Inventory, InventoryCountItem
from apps.operations.services.inventory_service import approve_inventory, InventoryApproveError,InventorySubmitError, submit_inventory
from django.template.response import TemplateResponse
from django.urls import reverse



@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "cns", "cpf", "ubs", "updated_at")
    list_filter = ("ubs",)
    search_fields = ("full_name", "cns", "cpf")

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)

        patient = self.get_object(request, object_id)
        if patient:
            # Aqui você pode decidir como obter a UBS de contexto
            # MVP: pega a primeira membership ativa do usuário
            membership = request.user.ubs_memberships.filter(active=True).select_related("ubs").first()

            if membership:
                ubs = membership.ubs

                auth = has_ubs_perm(
                    user=request.user,
                    ubs=ubs,
                    perm_codename="view_patient_full",
                    app_label="operations",
                )

                if auth.allowed:
                    log_event(
                        ubs=ubs,
                        actor=request.user,
                        event="patient.view_full",
                        object_type="operations.Patient",
                        object_id=patient.id,
                        payload={
                            "cpf": patient.cpf,
                            "has_phone": bool(patient.phone),
                        },
                        request=request,
                    )

        return response



@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("patient", "prescriber_name", "origin_unit", "prescription_date", "ubs", "created_at")
    list_filter = ("ubs", "prescription_date")
    search_fields = ("patient__full_name", "prescriber_name", "origin_unit")


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1

class DispensationItemInline(admin.TabularInline):
    model = DispensationItem
    extra = 1
    fields = ("medicine", "batch", "quantity")  # mantém simples por enquanto


class InventoryCountItemInline(admin.TabularInline):
    model = InventoryCountItem
    extra = 1


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "supplier_name", "receipt_date", "status", "ubs", "updated_at", "finalize_button")
    list_filter = ("ubs", "status")
    search_fields = ("invoice_number", "supplier_name", "access_key")
    inlines = [InvoiceItemInline]

    def finalize_button(self, obj):
        if obj.status == obj.STATUS_DRAFT:
            return format_html('<a class="button" href="{}">Finalizar</a>', f"{obj.id}/finalize/")
        return "-"
        finalize_button.short_description = "Ação"
        finalize_button.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("<uuid:invoice_id>/finalize/", self.admin_site.admin_view(self.finalize_view), name="invoice-finalize"),
        ]
        return custom_urls + urls

    def finalize_view(self, request, invoice_id):
        invoice = Invoice.objects.select_related("ubs").filter(id=invoice_id).first()
        if not invoice:
            self.message_user(request, "NF não encontrada.", level=messages.ERROR)
            return redirect("../..")

        # UBS de contexto = da própria NF
        ubs = invoice.ubs

        try:
            finalize_invoice(invoice_id=invoice.id, user=request.user, ubs=ubs)
            self.message_user(request, f"NF {invoice.invoice_number} finalizada e estoque atualizado.", level=messages.SUCCESS)
        except InvoiceFinalizeError as e:
            self.message_user(request, f"Falha ao finalizar: {e}", level=messages.ERROR)

        return redirect("../..")





@admin.register(Dispensation)
class DispensationAdmin(admin.ModelAdmin):
    list_display = (
        "patient_display",
        "status_display",
        "ubs_display",
        "stock_location_display",
        "created_at",
        "confirm_button",
    )
    list_filter = ("ubs", "status", "stock_location")
    search_fields = ("patient__full_name", "patient__cns")
    inlines = [DispensationItemInline]


    @admin.display(description="Paciente")
    def patient_display(self, obj):
        return obj.patient.full_name if obj.patient_id else "-"

    @admin.display(description="Status")
    def status_display(self, obj):
        # traduz o status sem mexer em choices
        mapping = {
            "DRAFT": "Rascunho",
            "CONFIRMED": "Confirmada",
            "CANCELLED": "Cancelada",
        }
        return mapping.get(obj.status, obj.status)

    @admin.display(description="UBS")
    def ubs_display(self, obj):
        return str(obj.ubs) if obj.ubs_id else "-"

    @admin.display(description="Local de Estoque")
    def stock_location_display(self, obj):
        return str(obj.stock_location) if obj.stock_location_id else "-"



    @admin.display(description="Ação")
    def confirm_button(self, obj):
        if obj.status == obj.STATUS_DRAFT:
            return format_html('<a class="button" href="{}">Confirmar</a>', f"{obj.id}/confirm/")
        return "-"

    # def confirm_button(self, obj):
    #     if obj.status == obj.STATUS_DRAFT:
    #         url = reverse("admin:dispensation-confirm", kwargs={"dispensation_id": str(obj.id)})
    #         return format_html('<a class="button" href="{}">Confirmar</a>', url)
    #     return "-"
    # confirm_button.short_description = "Ação"



    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("<uuid:dispensation_id>/confirm/", self.admin_site.admin_view(self.confirm_view), name="dispensation-confirm"),
        ]
        return custom_urls + urls

    def confirm_view(self, request, dispensation_id):

        disp = Dispensation.objects.select_related("ubs", "patient").filter(id=dispensation_id).first()
        if not disp:
            self.message_user(request, "Dispensação não encontrada.", level=messages.ERROR)
            return redirect("../..")

        try:
            # IMPORT AQUI (garante que é o arquivo que você está editando)
            from apps.operations.services.dispensation_service import (
                confirm_dispensation,
                DispensationConfirmError,
            )

            confirm_dispensation(dispensation_id=disp.id, user=request.user, ubs=disp.ubs)

            self.message_user(request, "Dispensação confirmada e estoque baixado.", level=messages.SUCCESS)
        except DispensationConfirmError as e:
            self.message_user(request, f"Falha ao confirmar: {e}", level=messages.ERROR)
        except Exception as e:
            # pra não mascarar erro inesperado
            self.message_user(request, f"Erro inesperado: {e}", level=messages.ERROR)

        return redirect("../..")



@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "ubs", "started_at", "finished_at", "submit_button", "approve_button")
    list_filter = ("ubs", "status")
    inlines = [InventoryCountItemInline]

    def approve_button(self, obj):
        if obj.status in [obj.STATUS_IN_PROGRESS, obj.STATUS_PENDING_APPROVAL]:
            return format_html('<a class="button" href="{}">Aprovar</a>', f"{obj.id}/approve/")
        return "-"
    approve_button.short_description = "Ação"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("<uuid:inventory_id>/approve/", self.admin_site.admin_view(self.approve_view), name="inventory-approve"),
            path("<uuid:inventory_id>/submit/", self.admin_site.admin_view(self.submit_view), name="inventory-submit"),
        ]
        return custom_urls + urls

    def approve_view(self, request, inventory_id):
        inv = Inventory.objects.select_related("ubs").filter(id=inventory_id).first()
        if not inv:
            self.message_user(request, "Inventário não encontrado.", level=messages.ERROR)
            return redirect("../..")

        # GET: mostra tela para motivo
        if request.method == "GET":
            inv_full = (
                Inventory.objects
                .select_related("ubs")
                .prefetch_related(
                    "count_items__stock_location",
                    "count_items__batch",
                    "count_items__batch__medicine",
                )
                .get(id=inv.id)
            )

            from decimal import Decimal
            from apps.stock.models import StockBatchBalance

            preview_rows = []
            adjustments_applied = 0

            for ci in inv_full.count_items.all():
                bb = StockBatchBalance.objects.filter(
                    stock_location=ci.stock_location,
                    batch=ci.batch,
                ).first()

                current_qty = (bb.quantity if bb else Decimal("0"))
                counted_qty = Decimal(ci.counted_quantity)
                diff = counted_qty - current_qty

                if diff != 0:
                    adjustments_applied += 1

                preview_rows.append({
                    "location_name": str(ci.stock_location),
                    "medicine_name": str(ci.batch.medicine),
                    "lot_number": ci.batch.lot_number,
                    "expiry_date": ci.batch.expiry_date,
                    "current_qty": current_qty,
                    "counted_qty": counted_qty,
                    "diff": diff,
                })

            context = dict(
                self.admin_site.each_context(request),
                inventory=inv,
                preview_rows=preview_rows,
                adjustments_applied=adjustments_applied,
            )
            return TemplateResponse(request, "admin/operations/inventory/approve_form.html", context)

        # GET: mostra tela para motivo
        # if request.method == "GET":
        #     context = dict(
        #         self.admin_site.each_context(request),
        #         inventory=inv,
        #     )
        #     return TemplateResponse(request, "admin/operations/inventory/approve_form.html", context)

        # POST: aprova com motivo
        reason = request.POST.get("reason")
        if not reason:
            self.message_user(request, "Motivo é obrigatório.", level=messages.ERROR)
            return redirect(request.path)

        try:
            approve_inventory(
                inventory_id=inv.id,
                user=request.user,
                ubs=inv.ubs,
                reason=reason,
            )
            self.message_user(request, "Inventário aprovado e ajuste aplicado no estoque.", level=messages.SUCCESS)
        except InventoryApproveError as e:
            self.message_user(request, f"Falha ao aprovar: {e}", level=messages.ERROR)

        return redirect("../..")

    def submit_button(self, obj):
        if obj.status == obj.STATUS_IN_PROGRESS:
            return format_html('<a class="button" href="{}">Enviar p/ aprovação</a>', f"{obj.id}/submit/")
        return "-"
        
        submit_button.short_description = "Envio"

    def submit_view(self, request, inventory_id):
        inv = Inventory.objects.select_related("ubs").filter(id=inventory_id).first()
        if not inv:
            self.message_user(request, "Inventário não encontrado.", level=messages.ERROR)
            return redirect("../..")

        if request.method == "GET":
            context = dict(self.admin_site.each_context(request), inventory=inv)
            return TemplateResponse(request, "admin/operations/inventory/submit_form.html", context)

        note = request.POST.get("note") or ""

        try:
            submit_inventory(
                inventory_id=inv.id,
                user=request.user,
                ubs=inv.ubs,
                note=note,
            )
            self.message_user(request, "Inventário enviado para aprovação.", level=messages.SUCCESS)
        except InventorySubmitError as e:
            self.message_user(request, f"Falha ao enviar: {e}", level=messages.ERROR)

        return redirect("../..")
