-- 001_initial.sql
-- Creates shipments and status_history tables.
-- Matches the existing database pattern (SERIAL IDs, existing tables use integer PKs).
-- Run: psql "$DATABASE_URL" -f supabase/migrations/001_initial.sql

-- Shipments table
CREATE TABLE IF NOT EXISTS shipments (
    id SERIAL PRIMARY KEY,
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

-- Status history table
CREATE TABLE IF NOT EXISTS status_history (
    id SERIAL PRIMARY KEY,
    shipment_id INTEGER NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
        SELECT 1 FROM pg_trigger WHERE tgname = 'set_updated_at_shipments'
    ) THEN
        CREATE TRIGGER set_updated_at_shipments
            BEFORE UPDATE ON shipments
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at();
    END IF;
END;
$$;

-- Row Level Security (service role key bypasses RLS)
ALTER TABLE shipments ENABLE ROW LEVEL SECURITY;
ALTER TABLE status_history ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'shipments' AND policyname = 'Deny direct access'
    ) THEN
        CREATE POLICY "Deny direct access" ON shipments FOR ALL USING (false);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'status_history' AND policyname = 'Deny direct access'
    ) THEN
        CREATE POLICY "Deny direct access" ON status_history FOR ALL USING (false);
    END IF;
END;
$$;

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status);
CREATE INDEX IF NOT EXISTS idx_shipments_created_at ON shipments(created_at);
CREATE INDEX IF NOT EXISTS idx_shipments_venue_id ON shipments(venue_id);
CREATE INDEX IF NOT EXISTS idx_status_history_shipment_id ON status_history(shipment_id);
