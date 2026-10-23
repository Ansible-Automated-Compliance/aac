-- oracle_stig_collect.sql — DISA STIG Oracle Database 19c fact collection
--
-- Run by ansible/tasks/collect_oracle_db_facts.yml as the Oracle software owner:
--   sqlplus -S -L / as sysdba @oracle_stig_collect.sql
-- Every statement prints ONE fact as a line  @@<fact>@@<json>  (a long CLOB may
-- wrap; the mapper re-joins continuation lines). Each query is the check query
-- the STIG itself prescribes (V1R6, tools/stig_generators catalog), or the view
-- it names. Read-only: nothing here changes the database.
-- A statement that errors (view absent, non-CDB) prints nothing for its fact,
-- and the policy reports that control Open — fail closed, never fabricated.
SET PAGESIZE 0 LINESIZE 32767 LONG 20000000 LONGCHUNKSIZE 32767 TRIMSPOOL ON TRIMOUT ON
SET FEEDBACK OFF HEADING OFF ECHO OFF VERIFY OFF TERMOUT ON WRAP ON TAB OFF
SET SERVEROUTPUT OFF
WHENEVER SQLERROR CONTINUE
WHENEVER OSERROR CONTINUE

-- O19C-00-008600: instance name and version
SELECT '@@instance@@' || JSON_OBJECT('instance_name' VALUE instance_name, 'version' VALUE version,
       'host_name' VALUE host_name, 'status' VALUE status) FROM v$instance;

-- parameters the STIG reads (O19C-00-000300, 001800, 009200, 009300, 009400, 010400, 011300, 011500, 015500, 016000)
SELECT '@@parameters@@' || JSON_OBJECTAGG(LOWER(name) VALUE NVL(value, '') RETURNING CLOB)
  FROM v$parameter
 WHERE LOWER(name) IN ('max_idle_time','audit_trail','remote_os_roles','remote_os_authent','os_roles','sql92_security',
                       'remote_login_passwordfile','audit_sys_operations','dbfips_140','diagnostic_dest',
                       'log_archive_dest','log_archive_duplex_dest','db_recovery_file_dest','unified_audit_sga_queue_size')
    OR LOWER(name) LIKE 'log_archive_dest_%';

-- O19C-00-010500: _TRACE_FILES_PUBLIC is a hidden parameter (x$ as SYSDBA)
SELECT '@@hidden_parameters@@' || JSON_OBJECTAGG(LOWER(i.ksppinm) VALUE NVL(v.ksppstvl, '') RETURNING CLOB)
  FROM sys.x$ksppi i, sys.x$ksppcv v
 WHERE i.indx = v.indx AND LOWER(i.ksppinm) IN ('_trace_files_public');

-- O19C-00-000100, 012300, 012400, 012500, 013900, 014700: every profile, DEFAULT resolved
-- to the DEFAULT profile's value (the STIG's own effective-lifetime script)
SELECT '@@profiles@@' || JSON_OBJECTAGG(profile VALUE limits RETURNING CLOB)
  FROM (SELECT p.profile,
               JSON_OBJECTAGG(p.resource_name VALUE CASE WHEN p.limit = 'DEFAULT' THEN d.limit ELSE p.limit END RETURNING CLOB) AS limits
          FROM dba_profiles p
          JOIN dba_profiles d ON d.profile = 'DEFAULT' AND d.resource_name = p.resource_name
         GROUP BY p.profile);

-- which profile each open account uses (context for the report, not a control)
SELECT '@@user_profiles@@' || JSON_OBJECTAGG(username VALUE profile RETURNING CLOB)
  FROM dba_users WHERE oracle_maintained = 'N';

-- O19C-00-001800 / 011300: auditing
SELECT '@@unified_auditing_option@@' || JSON_OBJECT('value' VALUE value) FROM v$option WHERE parameter = 'Unified Auditing';
SELECT '@@unified_audit_policies_enabled@@' || NVL(JSON_ARRAYAGG(DISTINCT policy_name RETURNING CLOB), '[]')
  FROM audit_unified_enabled_policies;
SELECT '@@unified_audit_sys_policies@@' || JSON_OBJECT('count' VALUE COUNT(*)) FROM audit_unified_enabled_policies WHERE entity_name = 'SYS';

-- O19C-00-008200: object owners that are not Oracle-maintained (the site's authorized list is subtracted by the mapper)
SELECT '@@object_owners@@' || NVL(JSON_ARRAYAGG(owner ORDER BY owner RETURNING CLOB), '[]')
  FROM (SELECT DISTINCT o.owner FROM dba_objects o
         WHERE o.owner NOT IN (SELECT username FROM dba_users WHERE oracle_maintained = 'Y'));

-- O19C-00-008300: administrative privileges granted directly to accounts (the STIG's query and exclusion list)
SELECT '@@direct_admin_privileges@@' || NVL(JSON_ARRAYAGG(JSON_OBJECT('grantee' VALUE grantee, 'privilege' VALUE privilege) ORDER BY grantee, privilege RETURNING CLOB), '[]')
  FROM dba_sys_privs
 WHERE grantee IN (SELECT username FROM dba_users WHERE oracle_maintained = 'N'
                      AND username NOT IN ('XDB','SYSTEM','SYS','LBACSYS','DVSYS','DVF','SYSMAN_RO','SYSMAN_BIPLATFORM','SYSMAN_MDS',
                        'SYSMAN_OPSS','SYSMAN_STB','DBSNMP','SYSMAN','APEX_040200','WMSYS','SYSDG','SYSBACKUP','SPATIAL_WFS_ADMIN_USR',
                        'SPATIAL_CSW_ADMIN_US','GSMCATUSER','OLAPSYS','SI_INFORMTN_SCHEMA','OUTLN','ORDSYS','ORDDATA','OJVMSYS','ORACLE_OCM',
                        'MDSYS','ORDPLUGINS','GSMADMIN_INTERNAL','MDDATA','FLOWS_FILES','DIP','CTXSYS','AUDSYS','APPQOSSYS','APEX_PUBLIC_USER',
                        'ANONYMOUS','SPATIAL_CSW_ADMIN_USR','SYSKM','SYSMAN_TYPES','MGMT_VIEW','EUS_ENGINE_USER','EXFSYS','SYSMAN_APM'))
   AND privilege NOT IN ('UNLIMITED TABLESPACE','REFERENCES','INDEX','SYSDBA','SYSOPER','CREATE SESSION');

-- O19C-00-008700: database links
SELECT '@@db_links@@' || NVL(JSON_ARRAYAGG(JSON_OBJECT('owner' VALUE owner, 'db_link' VALUE db_link, 'host' VALUE host) ORDER BY owner, db_link RETURNING CLOB), '[]')
  FROM dba_db_links;

-- O19C-00-009000: WITH GRANT OPTION held by non-owners, non-DBAs (the STIG's query)
SELECT '@@grantable_privileges_non_dba@@' || NVL(JSON_ARRAYAGG(grantee || ': ' || owner || '.' || table_name ORDER BY grantee RETURNING CLOB), '[]')
  FROM dba_tab_privs
 WHERE grantable = 'YES'
   AND grantee NOT IN (SELECT DISTINCT owner FROM dba_objects)
   AND grantee NOT IN (SELECT grantee FROM dba_role_privs WHERE granted_role = 'DBA')
   AND table_name NOT LIKE 'SYS_PLSQL_%';

-- O19C-00-009500: system privileges WITH ADMIN OPTION (the STIG's query)
SELECT '@@admin_option_system_privileges@@' || NVL(JSON_ARRAYAGG(JSON_OBJECT('grantee' VALUE grantee, 'privilege' VALUE privilege) ORDER BY grantee, privilege RETURNING CLOB), '[]')
  FROM dba_sys_privs
 WHERE admin_option = 'YES'
   AND grantee NOT IN (SELECT username FROM dba_users WHERE oracle_maintained = 'Y')
   AND grantee NOT IN (SELECT role FROM dba_roles WHERE oracle_maintained = 'Y')
   AND grantee NOT IN ('DV_ACCTMGR','SCHEDULER_ADMIN','AQ_ADMINISTRATOR_ROLE');

-- O19C-00-009600: system privileges granted to PUBLIC
SELECT '@@public_system_privileges@@' || NVL(JSON_ARRAYAGG(privilege ORDER BY privilege RETURNING CLOB), '[]')
  FROM dba_sys_privs WHERE grantee = 'PUBLIC';

-- O19C-00-009700: roles WITH ADMIN OPTION (the STIG's query)
SELECT '@@admin_option_roles@@' || NVL(JSON_ARRAYAGG(JSON_OBJECT('grantee' VALUE grantee, 'granted_role' VALUE granted_role) ORDER BY grantee, granted_role RETURNING CLOB), '[]')
  FROM dba_role_privs
 WHERE admin_option = 'YES'
   AND grantee NOT IN (SELECT username FROM dba_users WHERE oracle_maintained = 'Y')
   AND grantee NOT IN (SELECT role FROM dba_roles WHERE oracle_maintained = 'Y')
   AND grantee NOT IN ('PDBUSER');

-- O19C-00-009800: object privileges granted to PUBLIC on non-Oracle schemas
SELECT '@@public_object_privileges@@' || NVL(JSON_ARRAYAGG(owner || '.' || table_name || ':' || privilege ORDER BY owner, table_name, privilege RETURNING CLOB), '[]')
  FROM dba_tab_privs
 WHERE grantee = 'PUBLIC'
   AND owner NOT IN (SELECT username FROM dba_users WHERE oracle_maintained = 'Y');

-- O19C-00-010000: roles granted to PUBLIC
SELECT '@@public_granted_roles@@' || NVL(JSON_ARRAYAGG(granted_role ORDER BY granted_role RETURNING CLOB), '[]')
  FROM dba_role_privs WHERE grantee = 'PUBLIC';

-- O19C-00-010100: default application administration roles (the STIG's query, Oracle-maintained accounts excluded)
SELECT '@@default_admin_roles@@' || NVL(JSON_ARRAYAGG(JSON_OBJECT('grantee' VALUE grantee, 'granted_role' VALUE granted_role) ORDER BY grantee, granted_role RETURNING CLOB), '[]')
  FROM dba_role_privs
 WHERE default_role = 'YES'
   AND granted_role IN (SELECT grantee FROM dba_sys_privs WHERE UPPER(privilege) LIKE '%USER%')
   AND grantee NOT IN (SELECT username FROM dba_users WHERE oracle_maintained = 'Y')
   AND grantee NOT IN (SELECT DISTINCT owner FROM dba_tables)
   AND grantee NOT IN (SELECT DISTINCT username FROM dba_users WHERE UPPER(account_status) LIKE '%LOCKED%');

-- O19C-00-011900: accounts still on their default password
SELECT '@@users_with_default_password@@' || NVL(JSON_ARRAYAGG(username ORDER BY username RETURNING CLOB), '[]')
  FROM sys.dba_users_with_defpwd WHERE username <> 'XS$NULL';

-- O19C-00-012900: sample schemas
SELECT '@@sample_schemas_present@@' || NVL(JSON_ARRAYAGG(username ORDER BY username RETURNING CLOB), '[]')
  FROM dba_users WHERE username IN ('BI','HR','OE','PM','IX','SH','SCOTT');

-- O19C-00-013000: installed components (the STIG's query)
SELECT '@@components@@' || NVL(JSON_ARRAYAGG(JSON_OBJECT('comp_id' VALUE comp_id, 'comp_name' VALUE comp_name, 'version' VALUE version, 'status' VALUE status) ORDER BY comp_id RETURNING CLOB), '[]')
  FROM dba_registry
 WHERE comp_id NOT IN ('CATJAVA','CATALOG','CATPROC','SDO','DV','XDB') AND status <> 'OPTION OFF';

-- O19C-00-013100: integrated options that are on
SELECT '@@options_enabled@@' || NVL(JSON_ARRAYAGG(parameter ORDER BY parameter RETURNING CLOB), '[]')
  FROM v$option
 WHERE parameter IN ('Data Mining','Oracle Database Extensions for .NET','OLAP','Partitioning','Real Application Testing')
   AND value = 'TRUE';

-- O19C-00-014800: 10G password verifiers
SELECT '@@users_with_10g_password_verifier@@' || NVL(JSON_ARRAYAGG(username ORDER BY username RETURNING CLOB), '[]')
  FROM dba_users WHERE password_versions LIKE '%10G%';

-- O19C-00-016700: archive log mode
SELECT '@@database@@' || JSON_OBJECT('name' VALUE name, 'log_mode' VALUE log_mode, 'cdb' VALUE cdb, 'force_logging' VALUE force_logging) FROM v$database;

-- O19C-00-016800 / 016900: tablespace encryption and the TDE wallet
SELECT '@@tablespaces@@' || NVL(JSON_ARRAYAGG(JSON_OBJECT('tablespace_name' VALUE tablespace_name, 'encrypted' VALUE encrypted) ORDER BY tablespace_name RETURNING CLOB), '[]')
  FROM dba_tablespaces
 WHERE contents NOT IN ('TEMPORARY','UNDO') AND tablespace_name NOT IN ('SYSTEM','SYSAUX');
SELECT '@@encryption_wallet@@' || NVL(JSON_ARRAYAGG(JSON_OBJECT('wrl_type' VALUE wrl_type, 'status' VALUE status, 'wallet_type' VALUE wallet_type) RETURNING CLOB), '[]')
  FROM v$encryption_wallet;

-- O19C-00-018600: applied SQL patches
SELECT '@@sqlpatches@@' || NVL(JSON_ARRAYAGG(JSON_OBJECT('patch_id' VALUE patch_id, 'action' VALUE action, 'status' VALUE status, 'description' VALUE description) ORDER BY action_time RETURNING CLOB), '[]')
  FROM dba_registry_sqlpatch;

-- O19C-00-020500 / 020600: control files and redo log groups
SELECT '@@control_files@@' || NVL(JSON_ARRAYAGG(name ORDER BY name RETURNING CLOB), '[]') FROM v$controlfile;
SELECT '@@redo_log_groups@@' || NVL(JSON_ARRAYAGG(JSON_OBJECT('group' VALUE group#, 'members' VALUE members) ORDER BY group# RETURNING CLOB), '[]')
  FROM (SELECT group#, JSON_ARRAYAGG(member ORDER BY member RETURNING CLOB) AS members FROM v$logfile GROUP BY group#);

-- directories the file-permission checks look at (O19C-00-007300, 010400, 011500, 017600)
SELECT '@@datafile_dirs@@' || NVL(JSON_ARRAYAGG(DISTINCT dir RETURNING CLOB), '[]')
  FROM (SELECT SUBSTR(name, 1, INSTR(name, '/', -1) - 1) AS dir FROM v$datafile
        UNION SELECT SUBSTR(name, 1, INSTR(name, '/', -1) - 1) FROM v$tempfile
        UNION SELECT SUBSTR(member, 1, INSTR(member, '/', -1) - 1) FROM v$logfile
        UNION SELECT SUBSTR(name, 1, INSTR(name, '/', -1) - 1) FROM v$controlfile);
SELECT '@@archive_dests@@' || NVL(JSON_ARRAYAGG(destination ORDER BY dest_id RETURNING CLOB), '[]')
  FROM v$archive_dest WHERE status = 'VALID' AND destination IS NOT NULL;

SELECT '@@collected_at@@' || JSON_OBJECT('at' VALUE TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')) FROM dual;
EXIT
