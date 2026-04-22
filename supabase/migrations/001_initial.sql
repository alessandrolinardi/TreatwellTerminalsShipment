-- 001_initial.sql
-- Creates plat_terminal_shipments and plat_terminal_shipments_status_history tables.
-- The plat_ prefix follows the shared-Supabase convention used by sibling projects
-- (see ~/Desktop/Workspace/wiki/knowledge/supabase-shared-db.md).
-- Run: psql "$DATABASE_URL" -f supabase/migrations/001_initial.sql

-- Shipments table
CREATE TABLE IF NOT EXISTS plat_terminal_shipments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id TEXT NOT NULL,
    supplier_id TEXT NOT NULL,
    address TEXT NOT NULL,
    contact_name TEXT DEFAULT '',
    serial_number TEXT DEFAULT '',
    tracking_number TEXT DEFAULT '',
    carrier TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT DEFAULT '',
    created_by TEXT DEFAULT 'Ale',
    assigned_to TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-update updated_at on every UPDATE
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'set_updated_at_plat_terminal_shipments'
    ) THEN
        CREATE TRIGGER set_updated_at_plat_terminal_shipments
            BEFORE UPDATE ON plat_terminal_shipments
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at();
    END IF;
END;
$$;

-- Status history table
CREATE TABLE IF NOT EXISTS plat_terminal_shipments_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipment_id UUID NOT NULL REFERENCES plat_terminal_shipments(id) ON DELETE CASCADE,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Row Level Security (service role key bypasses RLS)
ALTER TABLE plat_terminal_shipments ENABLE ROW LEVEL SECURITY;
ALTER TABLE plat_terminal_shipments_status_history ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'plat_terminal_shipments' AND policyname = 'Deny direct access'
    ) THEN
        CREATE POLICY "Deny direct access" ON plat_terminal_shipments FOR ALL USING (false);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'plat_terminal_shipments_status_history' AND policyname = 'Deny direct access'
    ) THEN
        CREATE POLICY "Deny direct access" ON plat_terminal_shipments_status_history FOR ALL USING (false);
    END IF;
END;
$$;

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_plat_terminal_shipments_status ON plat_terminal_shipments(status);
CREATE INDEX IF NOT EXISTS idx_plat_terminal_shipments_created_at ON plat_terminal_shipments(created_at);
CREATE INDEX IF NOT EXISTS idx_plat_terminal_shipments_venue_id ON plat_terminal_shipments(venue_id);
CREATE INDEX IF NOT EXISTS idx_plat_terminal_shipments_status_history_shipment_id ON plat_terminal_shipments_status_history(shipment_id);
