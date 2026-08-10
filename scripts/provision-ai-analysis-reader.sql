\if :{?app_role}
\else
\echo 'app_role psql variable is required'
\quit 2
\endif

DO $bootstrap$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = 'ai_do_analysis_reader'
    ) THEN
        CREATE ROLE ai_do_analysis_reader
            NOLOGIN
            NOINHERIT
            NOSUPERUSER
            NOCREATEROLE
            NOCREATEDB
            NOREPLICATION
            NOBYPASSRLS;
    END IF;
END;
$bootstrap$;

GRANT ai_do_analysis_reader TO :"app_role";
