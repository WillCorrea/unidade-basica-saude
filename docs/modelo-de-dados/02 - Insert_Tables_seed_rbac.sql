-- ============================================================
-- RBAC Seed - Sistema de Medicamentos UBS
-- Roles + Permissions + Role_Permissions
-- ============================================================

-- Requer: pgcrypto extension + tabelas roles/permissions/role_permissions já criadas
-- (No seu DDL já tem CREATE EXTENSION pgcrypto)

BEGIN;

-- ============================================================
-- 1) ROLES
-- ============================================================

INSERT INTO roles (id, code, name) VALUES
  (gen_random_uuid(), 'ADMIN',     'Administrador Municipal'),
  (gen_random_uuid(), 'RT',        'Responsável Técnico / Farmacêutico'),
  (gen_random_uuid(), 'ESTOQUE',   'Operador de Estoque'),
  (gen_random_uuid(), 'ATENDENTE', 'Atendente de Dispensação'),
  (gen_random_uuid(), 'AUDITOR',   'Auditor / Consulta')
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- 2) PERMISSIONS (lista padrão)
-- ============================================================

-- Estrutura (code, name, description)
WITH perms(code, name, description) AS (
  VALUES
  -- Organizacional / Cadastros
  ('ubs.view',                 'Ver UBS', 'Permite visualizar cadastro de UBS'),
  ('ubs.manage',               'Gerenciar UBS', 'Permite criar/editar/inativar UBS'),
  ('stock_location.view',      'Ver Locais de Estoque', 'Permite visualizar locais de estoque'),
  ('stock_location.manage',    'Gerenciar Locais de Estoque', 'Permite criar/editar/inativar locais'),
  ('user.manage',              'Gerenciar Usuários', 'Permite criar/editar/inativar usuários e vínculos'),
  ('role.manage',              'Gerenciar Roles', 'Permite administrar papéis'),
  ('permission.manage',        'Gerenciar Permissões', 'Permite administrar permissões'),

  -- Catálogo
  ('medicine.view',            'Ver Medicamentos', 'Permite consultar catálogo de medicamentos'),
  ('medicine.manage',          'Gerenciar Medicamentos', 'Permite cadastrar/editar/inativar medicamentos'),

  -- Estoque (consultas e operações)
  ('stock.view',               'Consultar Estoque', 'Permite visualizar saldos e disponibilidade'),
  ('stock.statement.view',     'Consultar Extrato', 'Permite consultar movimentações/extrato'),
  ('stock.transfer',           'Transferir Estoque', 'Permite transferir medicamentos entre locais'),
  ('stock.adjust.request',     'Solicitar Ajuste de Estoque', 'Permite gerar proposta de ajuste (inventário/divergências)'),
  ('stock.adjust.approve',     'Aprovar Ajuste de Estoque', 'Permite aprovar e aplicar ajustes'),
  ('stock.movement.reverse',   'Estornar Movimentação', 'Permite estornar movimentações registradas'),

  -- Nota Fiscal
  ('invoice.view',             'Ver Notas Fiscais', 'Permite consultar notas fiscais e itens'),
  ('invoice.create',           'Criar Nota Fiscal', 'Permite registrar nota fiscal e itens'),
  ('invoice.finalize',         'Finalizar Nota Fiscal', 'Permite finalizar/confirmar entrada no estoque'),
  ('invoice.cancel',           'Cancelar Nota Fiscal', 'Permite cancelar nota fiscal (quando aplicável)'),

  -- Paciente e prescrição (LGPD-friendly)
  ('patient.view_basic',       'Ver Paciente (Básico)', 'Permite ver dados mínimos (ex: CNS e nome)'),
  ('patient.view_full',        'Ver Paciente (Completo)', 'Permite ver dados completos (endereço/CPF etc.)'),
  ('patient.manage',           'Gerenciar Paciente', 'Permite criar/editar cadastro de paciente'),

  ('prescription.view',        'Ver Prescrições', 'Permite consultar prescrições'),
  ('prescription.create',      'Criar Prescrição', 'Permite registrar dados de prescrição'),

  -- Dispensação
  ('dispensation.view',        'Ver Dispensações', 'Permite consultar dispensações'),
  ('dispensation.create',      'Criar Dispensação', 'Permite iniciar e montar dispensação (itens)'),
  ('dispensation.confirm',     'Confirmar Dispensação', 'Permite confirmar dispensação e baixar estoque'),

  -- Inventário
  ('inventory.view',           'Ver Inventários', 'Permite consultar inventários'),
  ('inventory.create',         'Criar Inventário', 'Permite iniciar inventário por local'),
  ('inventory.count',          'Registrar Contagem', 'Permite lançar contagem física'),
  ('inventory.approve',        'Aprovar Inventário', 'Permite aprovar/rejeitar inventário'),

  -- Auditoria e Relatórios
  ('audit.view',               'Ver Auditoria', 'Permite consultar logs de auditoria'),
  ('audit.export',             'Exportar Auditoria', 'Permite exportar logs'),
  ('report.view',              'Ver Relatórios', 'Permite gerar relatórios'),
  ('report.export',            'Exportar Relatórios', 'Permite exportar relatórios (PDF/CSV)')
)
INSERT INTO permissions (id, code, name, description, created_at, updated_at)
SELECT gen_random_uuid(), p.code, p.name, p.description, now(), now()
FROM perms p
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- 3) ROLE_PERMISSIONS (mapeamento por papel)
-- ============================================================

-- Helpers para buscar ids
WITH
r AS (
  SELECT id, code FROM roles
),
p AS (
  SELECT id, code FROM permissions
),
rp(role_code, perm_code) AS (
  VALUES
  -- ========================================================
  -- ADMIN: tudo (recomendado para prefeitura/gestão)
  -- ========================================================
  ('ADMIN','ubs.view'),
  ('ADMIN','ubs.manage'),
  ('ADMIN','stock_location.view'),
  ('ADMIN','stock_location.manage'),
  ('ADMIN','user.manage'),
  ('ADMIN','role.manage'),
  ('ADMIN','permission.manage'),

  ('ADMIN','medicine.view'),
  ('ADMIN','medicine.manage'),

  ('ADMIN','stock.view'),
  ('ADMIN','stock.statement.view'),
  ('ADMIN','stock.transfer'),
  ('ADMIN','stock.adjust.request'),
  ('ADMIN','stock.adjust.approve'),
  ('ADMIN','stock.movement.reverse'),

  ('ADMIN','invoice.view'),
  ('ADMIN','invoice.create'),
  ('ADMIN','invoice.finalize'),
  ('ADMIN','invoice.cancel'),

  ('ADMIN','patient.view_basic'),
  ('ADMIN','patient.view_full'),
  ('ADMIN','patient.manage'),
  ('ADMIN','prescription.view'),
  ('ADMIN','prescription.create'),

  ('ADMIN','dispensation.view'),
  ('ADMIN','dispensation.create'),
  ('ADMIN','dispensation.confirm'),

  ('ADMIN','inventory.view'),
  ('ADMIN','inventory.create'),
  ('ADMIN','inventory.count'),
  ('ADMIN','inventory.approve'),

  ('ADMIN','audit.view'),
  ('ADMIN','audit.export'),
  ('ADMIN','report.view'),
  ('ADMIN','report.export'),

  -- ========================================================
  -- RT: controle, aprovação, auditoria, estorno
  -- ========================================================
  ('RT','ubs.view'),
  ('RT','stock_location.view'),

  ('RT','medicine.view'),
  ('RT','medicine.manage'),

  ('RT','stock.view'),
  ('RT','stock.statement.view'),
  ('RT','stock.transfer'),           -- opcional (se RT puder transferir)
  ('RT','stock.adjust.request'),
  ('RT','stock.adjust.approve'),
  ('RT','stock.movement.reverse'),

  ('RT','invoice.view'),
  ('RT','invoice.create'),           -- opcional (se RT puder registrar NF)
  ('RT','invoice.finalize'),
  ('RT','invoice.cancel'),           -- opcional

  ('RT','patient.view_basic'),
  ('RT','patient.view_full'),
  ('RT','patient.manage'),

  ('RT','prescription.view'),
  ('RT','prescription.create'),

  ('RT','dispensation.view'),        -- leitura para auditoria/controle
  ('RT','inventory.view'),
  ('RT','inventory.create'),         -- opcional
  ('RT','inventory.count'),          -- opcional
  ('RT','inventory.approve'),

  ('RT','audit.view'),
  ('RT','audit.export'),
  ('RT','report.view'),
  ('RT','report.export'),

  -- ========================================================
  -- ESTOQUE: entrada, transferência, inventário (sem estorno)
  -- ========================================================
  ('ESTOQUE','ubs.view'),
  ('ESTOQUE','stock_location.view'),

  ('ESTOQUE','medicine.view'),

  ('ESTOQUE','stock.view'),
  ('ESTOQUE','stock.statement.view'),
  ('ESTOQUE','stock.transfer'),
  ('ESTOQUE','stock.adjust.request'),

  ('ESTOQUE','invoice.view'),
  ('ESTOQUE','invoice.create'),
  ('ESTOQUE','invoice.finalize'),

  ('ESTOQUE','inventory.view'),
  ('ESTOQUE','inventory.create'),
  ('ESTOQUE','inventory.count'),

  ('ESTOQUE','report.view'),         -- leitura de relatórios operacionais (opcional)

  -- ========================================================
  -- ATENDENTE: dispensação e visão básica do paciente
  -- ========================================================
  ('ATENDENTE','stock.view'),         -- para ver disponibilidade
  ('ATENDENTE','stock.statement.view'), -- opcional (pode remover se não quiser)
  ('ATENDENTE','medicine.view'),

  ('ATENDENTE','patient.view_basic'),
  ('ATENDENTE','patient.manage'),     -- permite cadastro rápido / completar depois (ajuste se quiser)
  ('ATENDENTE','prescription.create'),
  ('ATENDENTE','prescription.view'),

  ('ATENDENTE','dispensation.view'),
  ('ATENDENTE','dispensation.create'),
  ('ATENDENTE','dispensation.confirm'),

  -- ========================================================
  -- AUDITOR: somente leitura (estoque, auditoria, relatórios)
  -- ========================================================
  ('AUDITOR','ubs.view'),
  ('AUDITOR','stock_location.view'),
  ('AUDITOR','medicine.view'),

  ('AUDITOR','stock.view'),
  ('AUDITOR','stock.statement.view'),

  ('AUDITOR','audit.view'),
  ('AUDITOR','report.view'),
  ('AUDITOR','report.export')         -- opcional
)
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT
  gen_random_uuid(),
  r.id,
  p.id,
  now()
FROM rp
JOIN r ON r.code = rp.role_code
JOIN p ON p.code = rp.perm_code
ON CONFLICT (role_id, permission_id) DO NOTHING;

COMMIT;

-- ============================================================
-- Observações rápidas:
-- 1) Se quiser restringir o ATENDENTE a não editar paciente completo,
--    remova patient.manage e mantenha somente patient.view_basic + um fluxo de "cadastro rápido" via serviço.
-- 2) Se quiser que somente RT/Admin finalize NF ou faça transferência, ajuste as permissões acima.
-- ============================================================
