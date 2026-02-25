const express = require('express');
const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 3000;

// Ensure data directory exists
const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir);

// Initialize SQLite
const db = new Database(path.join(dataDir, 'shipments.db'));
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

// Create tables
db.exec(`
  CREATE TABLE IF NOT EXISTS shipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shipment_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (shipment_id) REFERENCES shipments(id)
  );
`);

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// --- API Routes ---

// List all shipments (with optional status filter)
app.get('/api/shipments', (req, res) => {
  const { status } = req.query;
  let rows;
  if (status && status !== 'all') {
    rows = db.prepare('SELECT * FROM shipments WHERE status = ? ORDER BY updated_at DESC').all(status);
  } else {
    rows = db.prepare('SELECT * FROM shipments ORDER BY updated_at DESC').all();
  }
  res.json(rows);
});

// Get single shipment with history
app.get('/api/shipments/:id', (req, res) => {
  const shipment = db.prepare('SELECT * FROM shipments WHERE id = ?').get(req.params.id);
  if (!shipment) return res.status(404).json({ error: 'Shipment not found' });
  const history = db.prepare('SELECT * FROM status_history WHERE shipment_id = ? ORDER BY created_at DESC').all(req.params.id);
  res.json({ ...shipment, history });
});

// Create a new shipment (Ale enters info from Treatwell)
app.post('/api/shipments', (req, res) => {
  const { venue_id, supplier_id, address, contact_name, notes, created_by } = req.body;
  if (!venue_id || !supplier_id || !address) {
    return res.status(400).json({ error: 'venue_id, supplier_id, and address are required' });
  }
  const stmt = db.prepare(`
    INSERT INTO shipments (venue_id, supplier_id, address, contact_name, notes, created_by)
    VALUES (?, ?, ?, ?, ?, ?)
  `);
  const result = stmt.run(venue_id, supplier_id, address, contact_name || '', notes || '', created_by || 'Ale');

  // Log initial status
  db.prepare('INSERT INTO status_history (shipment_id, new_status, changed_by, note) VALUES (?, ?, ?, ?)')
    .run(result.lastInsertRowid, 'pending', created_by || 'Ale', 'Shipment created');

  const shipment = db.prepare('SELECT * FROM shipments WHERE id = ?').get(result.lastInsertRowid);
  res.status(201).json(shipment);
});

// Update a shipment (employee fills in serial number, tracking, status, etc.)
app.patch('/api/shipments/:id', (req, res) => {
  const shipment = db.prepare('SELECT * FROM shipments WHERE id = ?').get(req.params.id);
  if (!shipment) return res.status(404).json({ error: 'Shipment not found' });

  const allowed = ['venue_id', 'supplier_id', 'address', 'contact_name', 'serial_number', 'tracking_number', 'carrier', 'status', 'notes', 'assigned_to'];
  const updates = [];
  const values = [];

  for (const field of allowed) {
    if (req.body[field] !== undefined) {
      updates.push(`${field} = ?`);
      values.push(req.body[field]);
    }
  }

  if (updates.length === 0) return res.status(400).json({ error: 'No valid fields to update' });

  updates.push("updated_at = datetime('now')");
  values.push(req.params.id);

  db.prepare(`UPDATE shipments SET ${updates.join(', ')} WHERE id = ?`).run(...values);

  // Log status change if status was updated
  if (req.body.status && req.body.status !== shipment.status) {
    db.prepare('INSERT INTO status_history (shipment_id, old_status, new_status, changed_by, note) VALUES (?, ?, ?, ?, ?)')
      .run(req.params.id, shipment.status, req.body.status, req.body.changed_by || '', req.body.status_note || '');
  }

  const updated = db.prepare('SELECT * FROM shipments WHERE id = ?').get(req.params.id);
  res.json(updated);
});

// Delete a shipment
app.delete('/api/shipments/:id', (req, res) => {
  const shipment = db.prepare('SELECT * FROM shipments WHERE id = ?').get(req.params.id);
  if (!shipment) return res.status(404).json({ error: 'Shipment not found' });
  db.prepare('DELETE FROM status_history WHERE shipment_id = ?').run(req.params.id);
  db.prepare('DELETE FROM shipments WHERE id = ?').run(req.params.id);
  res.json({ success: true });
});

// Fallback to index.html for SPA
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Treatwell Terminal Shipment Tracker running on http://localhost:${PORT}`);
});
