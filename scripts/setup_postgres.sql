-- Creates the application role and database for the FI/CO clone.
-- Run once as the PostgreSQL superuser:
--     psql -U postgres -f scripts/setup_postgres.sql
--
-- Safe to re-run: it skips objects that already exist.

DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sapfico') THEN
      CREATE ROLE sapfico LOGIN PASSWORD 'sapfico';
   END IF;
END
$$;

SELECT 'CREATE DATABASE sapfico OWNER sapfico'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sapfico')\gexec

GRANT ALL PRIVILEGES ON DATABASE sapfico TO sapfico;
