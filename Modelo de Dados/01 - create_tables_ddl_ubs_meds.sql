-- ============================================================
-- Sistema de Medicamentos - UBS (PostgreSQL)
-- DDL Completo (Consolidado)
-- ============================================================

-- Recomendado para gerar UUIDs
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- 1) TIPOS / DOMÍNIOS (opcional via CHECKs)
-- ============================================================

-- Se preferir ENUMs, dá pra trocar os CHECKs por CREATE TYPE.
-- Mantive CHECK para facilitar migração e portabilidade.

-- ============================================================
-- 2) ORGANIZACIONAL (TENANT / UBS / LOCAIS DE ESTOQUE)
-- ============================================================

CREATE TABLE tenants (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ubs (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
  name        text NOT NULL,
  cnes        text NULL,
  active      boolean NOT NULL DEFAULT true,

  -- Endereço
  address_street       text NULL,
  address_number       text NULL,
  address_neighborhood text NULL,
  address_city         text NULL,
  address_state        char(2) NULL,
  address_zip          text NULL,
  address_complement   text NULL,

  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_ubs_tenant ON ubs(tenant_id);
CREATE INDEX idx_ubs_active ON ubs(active);

CREATE TABLE stock_locations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ubs_id      uuid NOT NULL REFERENCES ubs(id) ON DELETE RESTRICT,
  name        text NOT NULL,
  active      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (ubs_id, name)
);

CREATE INDEX idx_stock_locations_ubs ON stock_locations(ubs_id);

-- ============================================================
-- 3) USUÁRIOS + RBAC FINO
-- ============================================================

CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username      text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  full_name     text NOT NULL,
  active        boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_active ON users(active);


-- Vínculo do usuário com UBS + grupo do Django (role)
CREATE TABLE user_ubs_groups (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES auth_user(id) ON DELETE RESTRICT,
  ubs_id      uuid NOT NULL REFERENCES ubs(id) ON DELETE RESTRICT,
  group_id    integer NOT NULL REFERENCES auth_group(id) ON DELETE RESTRICT,
  active      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, ubs_id, group_id)
);

CREATE INDEX idx_user_ubs_groups_user ON user_ubs_groups(user_id);
CREATE INDEX idx_user_ubs_groups_ubs  ON user_ubs_groups(ubs_id);
CREATE INDEX idx_user_ubs_groups_group ON user_ubs_groups(group_id);

-- ============================================================
-- 4) CATÁLOGO (MEDICAMENTOS / LOTES)
-- ============================================================

CREATE TABLE medicines (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
  name         text NOT NULL,
  presentation text NOT NULL, -- ex: comprimido, frasco
  unit         text NOT NULL, -- ex: un, ml, mg
  active       boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name, presentation, unit)
);

CREATE INDEX idx_medicines_tenant ON medicines(tenant_id);
CREATE INDEX idx_medicines_active ON medicines(active);

CREATE TABLE batches (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
  medicine_id  uuid NOT NULL REFERENCES medicines(id) ON DELETE RESTRICT,
  batch_number text NOT NULL,
  expiry_date  date NOT NULL,
  manufacturer text NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, medicine_id, batch_number, expiry_date)
);

CREATE INDEX idx_batches_medicine_expiry ON batches(medicine_id, expiry_date);
CREATE INDEX idx_batches_tenant ON batches(tenant_id);

-- ============================================================
-- 5) ESTOQUE (SALDO POR LOCAL + LOTE)
-- ============================================================

CREATE TABLE stock_balances (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ubs_id            uuid NOT NULL REFERENCES ubs(id) ON DELETE RESTRICT,
  stock_location_id uuid NOT NULL REFERENCES stock_locations(id) ON DELETE RESTRICT,
  batch_id          uuid NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,
  quantity          numeric(18,3) NOT NULL DEFAULT 0,
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (stock_location_id, batch_id),
  CHECK (quantity >= 0)
);

CREATE INDEX idx_stock_balances_location ON stock_balances(stock_location_id);
CREATE INDEX idx_stock_balances_batch ON stock_balances(batch_id);

-- ============================================================
-- 6) MOVIMENTAÇÕES DE ESTOQUE
-- ============================================================

CREATE TABLE stock_movements (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ubs_id             uuid NOT NULL REFERENCES ubs(id) ON DELETE RESTRICT,

  movement_type      text NOT NULL CHECK (movement_type IN ('ENTRADA','SAIDA','TRANSFERENCIA','AJUSTE','ESTORNO')),

  source_location_id uuid NULL REFERENCES stock_locations(id) ON DELETE RESTRICT,
  target_location_id uuid NULL REFERENCES stock_locations(id) ON DELETE RESTRICT,

  reference_type     text NULL CHECK (reference_type IS NULL OR reference_type IN ('NF','DISPENSACAO','INVENTARIO','MANUAL')),
  reference_id       uuid NULL, -- polimórfico (sem FK)

  reason             text NULL,
  created_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_stock_movements_ubs_date ON stock_movements(ubs_id, created_at DESC);
CREATE INDEX idx_stock_movements_ref ON stock_movements(reference_type, reference_id);
CREATE INDEX idx_stock_movements_source ON stock_movements(source_location_id);
CREATE INDEX idx_stock_movements_target ON stock_movements(target_location_id);

CREATE TABLE stock_movement_items (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stock_movement_id uuid NOT NULL REFERENCES stock_movements(id) ON DELETE CASCADE,
  batch_id          uuid NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,
  quantity          numeric(18,3) NOT NULL CHECK (quantity > 0),
  unit_cost         numeric(18,2) NULL CHECK (unit_cost IS NULL OR unit_cost >= 0),
  note              text NULL
);

CREATE INDEX idx_stock_movement_items_movement ON stock_movement_items(stock_movement_id);
CREATE INDEX idx_stock_movement_items_batch ON stock_movement_items(batch_id);

-- ============================================================
-- 7) NOTA FISCAL (ENTRADA)
-- ============================================================

CREATE TABLE invoices (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ubs_id             uuid NOT NULL REFERENCES ubs(id) ON DELETE RESTRICT,
  supplier_name      text NOT NULL,
  invoice_number     text NOT NULL,
  series             text NULL,
  access_key         text NULL,
  issue_date         date NULL,
  receipt_date       date NOT NULL,
  status             text NOT NULL CHECK (status IN ('DRAFT','PARTIAL','FINALIZED','CANCELED')),
  created_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),

  -- Único recomendado (pode ser ajustado por regra local)
  UNIQUE (ubs_id, supplier_name, invoice_number, series)
);

CREATE INDEX idx_invoices_ubs_date ON invoices(ubs_id, receipt_date DESC);
CREATE INDEX idx_invoices_status ON invoices(status);

CREATE TABLE invoice_items (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id uuid NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  medicine_id uuid NOT NULL REFERENCES medicines(id) ON DELETE RESTRICT,
  batch_id   uuid NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,
  quantity   numeric(18,3) NOT NULL CHECK (quantity > 0),
  unit_cost  numeric(18,2) NULL CHECK (unit_cost IS NULL OR unit_cost >= 0)
);

CREATE INDEX idx_invoice_items_invoice ON invoice_items(invoice_id);
CREATE INDEX idx_invoice_items_batch ON invoice_items(batch_id);

-- ============================================================
-- 8) PACIENTES / PRESCRIÇÃO / DISPENSAÇÃO
-- ============================================================

CREATE TABLE patients (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
  cns         text NOT NULL,
  cpf         text NULL,
  full_name   text NOT NULL,
  mother_name text NULL,
  birth_date  date NULL,
  phone       text NULL,

  address_street       text NULL,
  address_number       text NULL,
  address_neighborhood text NULL,
  address_city         text NULL,
  address_state        char(2) NULL,
  address_zip          text NULL,
  address_complement   text NULL,

  is_quick_registration boolean NOT NULL DEFAULT false,

  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),

  UNIQUE (tenant_id, cns)
);

-- CPF único apenas quando informado
CREATE UNIQUE INDEX ux_patients_tenant_cpf_notnull
ON patients(tenant_id, cpf)
WHERE cpf IS NOT NULL;

CREATE INDEX idx_patients_tenant_name ON patients(tenant_id, full_name);

CREATE TABLE prescriptions (
  id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ubs_id                      uuid NOT NULL REFERENCES ubs(id) ON DELETE RESTRICT,
  patient_id                  uuid NOT NULL REFERENCES patients(id) ON DELETE RESTRICT,

  prescriber_name             text NOT NULL,
  prescriber_registry_type    text NULL, -- CRM/COREN/CRO/OUTRO
  prescriber_registry_number  text NULL,

  origin_unit                 text NOT NULL,
  prescription_type           text NOT NULL,
  prescription_date           date NOT NULL,
  prescription_number         text NULL,

  attachment_path             text NULL,

  created_by_user_id          uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at                  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_prescriptions_patient_date ON prescriptions(patient_id, prescription_date DESC);
CREATE INDEX idx_prescriptions_ubs_date ON prescriptions(ubs_id, created_at DESC);

CREATE TABLE dispensations (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ubs_id             uuid NOT NULL REFERENCES ubs(id) ON DELETE RESTRICT,
  stock_location_id  uuid NOT NULL REFERENCES stock_locations(id) ON DELETE RESTRICT,

  patient_id         uuid NOT NULL REFERENCES patients(id) ON DELETE RESTRICT,
  prescription_id    uuid NOT NULL REFERENCES prescriptions(id) ON DELETE RESTRICT,

  status             text NOT NULL CHECK (status IN ('CONFIRMED','CANCELED','REVERSED')),

  created_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_dispensations_patient_date ON dispensations(patient_id, created_at DESC);
CREATE INDEX idx_dispensations_ubs_date ON dispensations(ubs_id, created_at DESC);
CREATE INDEX idx_dispensations_location ON dispensations(stock_location_id);

CREATE TABLE dispensation_items (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dispensation_id     uuid NOT NULL REFERENCES dispensations(id) ON DELETE CASCADE,
  medicine_id         uuid NOT NULL REFERENCES medicines(id) ON DELETE RESTRICT,
  batch_id            uuid NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,
  quantity            numeric(18,3) NOT NULL CHECK (quantity > 0),

  lot_selection_mode  text NOT NULL CHECK (lot_selection_mode IN ('FEFO','MANUAL')),
  lot_change_reason   text NULL
);

-- Regra: se MANUAL, motivo obrigatório (check simples)
ALTER TABLE dispensation_items
  ADD CONSTRAINT ck_lot_change_reason_required
  CHECK (
    (lot_selection_mode = 'FEFO' AND (lot_change_reason IS NULL OR length(trim(lot_change_reason)) = 0))
    OR
    (lot_selection_mode = 'MANUAL' AND lot_change_reason IS NOT NULL AND length(trim(lot_change_reason)) > 0)
  );

CREATE INDEX idx_disp_items_dispensation ON dispensation_items(dispensation_id);
CREATE INDEX idx_disp_items_batch ON dispensation_items(batch_id);

-- ============================================================
-- 9) INVENTÁRIO
-- ============================================================

CREATE TABLE inventories (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ubs_id             uuid NOT NULL REFERENCES ubs(id) ON DELETE RESTRICT,
  stock_location_id  uuid NOT NULL REFERENCES stock_locations(id) ON DELETE RESTRICT,

  status             text NOT NULL CHECK (status IN ('IN_PROGRESS','PENDING_APPROVAL','APPROVED','REJECTED','COMPLETED')),

  started_at         timestamptz NOT NULL DEFAULT now(),
  finished_at        timestamptz NULL,

  created_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  approved_by_user_id uuid NULL REFERENCES users(id) ON DELETE RESTRICT,
  approval_reason    text NULL,

  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_inventories_ubs_date ON inventories(ubs_id, created_at DESC);
CREATE INDEX idx_inventories_location ON inventories(stock_location_id);
CREATE INDEX idx_inventories_status ON inventories(status);

CREATE TABLE inventory_items (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  inventory_id            uuid NOT NULL REFERENCES inventories(id) ON DELETE CASCADE,
  batch_id                uuid NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,

  system_quantity_snapshot numeric(18,3) NOT NULL CHECK (system_quantity_snapshot >= 0),
  counted_quantity         numeric(18,3) NOT NULL CHECK (counted_quantity >= 0),
  difference_quantity      numeric(18,3) NOT NULL,

  note                    text NULL,

  UNIQUE (inventory_id, batch_id)
);

CREATE INDEX idx_inventory_items_inventory ON inventory_items(inventory_id);
CREATE INDEX idx_inventory_items_batch ON inventory_items(batch_id);

-- ============================================================
-- 10) ESTORNO (REVERSAL DE MOVIMENTAÇÃO)
-- ============================================================

CREATE TABLE movement_reversals (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  original_movement_id uuid NOT NULL REFERENCES stock_movements(id) ON DELETE RESTRICT,
  reversal_movement_id uuid NOT NULL REFERENCES stock_movements(id) ON DELETE RESTRICT,
  reason               text NOT NULL,
  created_by_user_id   uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (original_movement_id),
  UNIQUE (reversal_movement_id)
);

CREATE INDEX idx_movement_reversals_original ON movement_reversals(original_movement_id);
CREATE INDEX idx_movement_reversals_reversal ON movement_reversals(reversal_movement_id);

-- ============================================================
-- 11) AUDITORIA
-- ============================================================

CREATE TABLE audit_logs (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ubs_id      uuid NULL REFERENCES ubs(id) ON DELETE RESTRICT,
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

  action      text NOT NULL, -- CREATE/UPDATE/DELETE/CONFIRM/APPROVE/EXPORT/LOGIN...
  entity_type text NOT NULL, -- PATIENT/DISPENSATION/INVOICE/MOVEMENT...
  entity_id   uuid NULL,

  before_data jsonb NULL,
  after_data  jsonb NULL,

  ip_address  text NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_logs_ubs_date ON audit_logs(ubs_id, created_at DESC);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_user_date ON audit_logs(user_id, created_at DESC);

-- ============================================================
-- 12) NOTAS IMPORTANTES (fora do SQL)
-- ============================================================
-- 1) updated_at: você pode manter no app ou criar triggers para auto-update.
-- 2) Estoque "nunca negativo": validação forte deve ocorrer via transação na aplicação
--    com lock (SELECT ... FOR UPDATE) em stock_balances.
-- 3) reference_id em stock_movements é polimórfico (sem FK). Isso é intencional.
-- ============================================================
