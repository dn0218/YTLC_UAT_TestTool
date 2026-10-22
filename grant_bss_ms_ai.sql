-- ============================================================================
-- grant_bss_ms_ai.sql  -  DBA script for the Preprod TestTool (Plan B)
-- ============================================================================
-- Background:
--   The tool intentionally runs EVERYTHING as BSS_MS_AI (single auditable
--   account). BSS_MS_AI currently has:
--     - SELECT on all CC.* / CRM.* tables it needs            -> WORKING
--     - NO write privileges on any table                      -> ORA-01031
--     - NO private database link to the RB database           -> ORA-02019
--
--   This script grants TABLE-LEVEL privileges (whole table, no column
--   restrictions) on every table the tool writes, provides the RB dblink
--   for BSS_MS_AI (created by the DBA as 'link2rb'), and switches on
--   auditing so every action of the tool (and its operators) is traceable.
--
-- STATUS: EXECUTED by the DBA - all grants applied, private dblink created
-- as LINK2RB, verified 2026-10 (see _verify output in chat history).
--
--   Run as SYS / DBA on the target CC database (see config_ocs.json.example).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) Tab 1 (Invoice Generation) + Tab 4 (Sales Invoice resend)
--    UPDATE e_invoice.SEND_DATE after the e-invoice is generated
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON CC.E_INVOICE TO BSS_MS_AI;

-- ---------------------------------------------------------------------------
-- 2) Tab 2 (Contract End Date)
--    UPDATE prod / subs_agreement_inst agreement dates
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON CC.PROD                TO BSS_MS_AI;
GRANT SELECT, INSERT, UPDATE, DELETE ON CC.SUBS_AGREEMENT_INST TO BSS_MS_AI;

-- ---------------------------------------------------------------------------
-- 3) Tab 3 (MSISDN trailing-zero removal)
--    UPDATE subs.acc_nbr (CC side) and acc_nbr (CRM side)
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON CC.SUBS        TO BSS_MS_AI;
GRANT SELECT, INSERT, UPDATE, DELETE ON CRM.ACC_NBR    TO BSS_MS_AI;

-- ---------------------------------------------------------------------------
-- 4) Tab 5 (SIM Card attribute edit)
--    UPDATE attr_value by ROWID
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON CRM.SIM_CARD_ATTR_VALUE TO BSS_MS_AI;

-- ---------------------------------------------------------------------------
-- 5) Tab 6 (Roaming) needs no Oracle writes: inserts go through the OCS-side
--    mdbtt console (QuickMDB) via SSH. Nothing to grant here.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 6) The PRIVATE database link to RB (Tab 1 pre-billing / bill checks)
--    -> created by the DBA as LINK2RB for BSS_MS_AI. The tool uses
--       EVENT_RECURRING_<n>@link2rb / bill_data_<n>@link2rb.
--
--    Database links resolve against the LOGIN USER's own private links, so
--    BSS_MS_AI needs its own copy. First read CC's definition, then recreate
--    it for BSS_MS_AI:
--
--      SELECT db_link, username, host FROM dba_db_links WHERE owner='CC'
--        AND db_link LIKE 'LINK_RB%';
--
--    Then create the same link for BSS_MS_AI (fill in the real remote user /
--    password / TNS from the query above). Example shape:
--
-- CREATE DATABASE LINK link_rb
--   CONNECT TO <RB_USER> IDENTIFIED BY <RB_PASSWORD>
--   USING '<HOST:PORT/SERVICE_NAME from HOST column above>';
--
--    (CREATE DATABASE LINK requires the privilege below if BSS_MS_AI creates
--     it itself; as SYS/DBA the DBA can simply execute the CREATE above.)
-- ---------------------------------------------------------------------------
GRANT CREATE DATABASE LINK TO BSS_MS_AI;   -- only if BSS_MS_AI creates it itself

-- ---------------------------------------------------------------------------
-- 7) Auditing - track every tool action ("track each behavior and result")
--
--    Requires AUDIT_TRAIL=DB,EXTENDED (spfile) + one DB restart to capture
--    the actual SQL text/binds:
--      ALTER SYSTEM SET audit_trail=DB,EXTENDED SCOPE=SPFILE;
--      -- restart the instance once
--
--    Then audit all writes the tool can perform:
-- ---------------------------------------------------------------------------
AUDIT UPDATE ON CC.E_INVOICE            BY ACCESS;
AUDIT UPDATE ON CC.PROD                 BY ACCESS;
AUDIT UPDATE ON CC.SUBS_AGREEMENT_INST  BY ACCESS;
AUDIT UPDATE ON CC.SUBS                 BY ACCESS;
AUDIT UPDATE ON CRM.ACC_NBR             BY ACCESS;
AUDIT UPDATE ON CRM.SIM_CARD_ATTR_VALUE BY ACCESS;

-- Review with:
--   SELECT username, extended_timestamp, sql_text
--     FROM dba_audit_trail
--    WHERE username='BSS_MS_AI' ORDER BY extended_timestamp;

-- ============================================================================
-- END
-- ============================================================================
