#!/bin/bash
set -e

echo "Starting database initialization for BOT service..."

# 1. Connect to the default 'postgres' db to create the Bot user and Database
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
    -- Create the user for the Bot service
    CREATE USER "$POSTGRES_BOT_USER" WITH ENCRYPTED PASSWORD '$POSTGRES_BOT_PASSWORD';
    
    -- Create the database for the Bot service
    CREATE DATABASE "$POSTGRES_BOT_DB";
    
    -- Grant privileges to the Bot user
    GRANT ALL PRIVILEGES ON DATABASE "$POSTGRES_BOT_DB" TO "$POSTGRES_BOT_USER";
EOSQL

# 2. Connect specifically to the newly created Bot database to enable extensions
psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" --dbname "$POSTGRES_BOT_DB" <<-EOSQL
    -- Enable pgvector extension if available
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_BOT_DB" <<-EOSQL
    -- Ensure the bot user owns the public schema in its own database
    ALTER SCHEMA public OWNER TO "$POSTGRES_BOT_USER";
EOSQL


echo "Database initialization complete! Created database: $POSTGRES_BOT_DB"
