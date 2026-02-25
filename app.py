import streamlit as st
import sqlite3
import os
from datetime import datetime

# --- Page config ---
st.set_page_config(
    page_title="Treatwell Terminal Shipments",
    page_icon="📦",
    layout="wide",
)

# --- Database setup ---
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "shipments.db")


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    conn = get_db()
    conn.executescript("""
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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_by TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (shipment_id) REFERENCES shipments(id)
        );
    """)
    conn.close()


init_db()

# --- Constants ---
STATUS_OPTIONS = {
    "pending": "🟡 Pending",
    "label_created": "🏷️ Label Created",
    "picked_up": "📦 Picked Up",
    "in_transit": "🚚 In Transit",
    "delivered": "✅ Delivered",
    "issue": "🔴 Issue",
}

STATUS_KEYS = list(STATUS_OPTIONS.keys())


def format_status(status):
    return STATUS_OPTIONS.get(status, status)


def format_date(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%d %b %Y %H:%M")
    except (ValueError, TypeError):
        return date_str


# --- DB helpers ---
def get_shipments(status_filter="all"):
    conn = get_db()
    if status_filter and status_filter != "all":
        rows = conn.execute(
            "SELECT * FROM shipments WHERE status = ? ORDER BY updated_at DESC",
            (status_filter,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM shipments ORDER BY updated_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_shipment(shipment_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_history(shipment_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM status_history WHERE shipment_id = ? ORDER BY created_at DESC",
        (shipment_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_shipment(venue_id, supplier_id, address, contact_name, notes, created_by):
    conn = get_db()
    ts = now()
    cur = conn.execute(
        """INSERT INTO shipments (venue_id, supplier_id, address, contact_name, notes, created_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (venue_id, supplier_id, address, contact_name, notes, created_by, ts, ts),
    )
    shipment_id = cur.lastrowid
    conn.execute(
        "INSERT INTO status_history (shipment_id, new_status, changed_by, note, created_at) VALUES (?, ?, ?, ?, ?)",
        (shipment_id, "pending", created_by, "Shipment created", ts),
    )
    conn.commit()
    conn.close()
    return shipment_id


def update_shipment(shipment_id, updates, changed_by="", status_note=""):
    conn = get_db()
    old = conn.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    if not old:
        conn.close()
        return False

    old_status = old["status"]
    allowed = [
        "venue_id", "supplier_id", "address", "contact_name",
        "serial_number", "tracking_number", "carrier",
        "status", "notes", "assigned_to",
    ]
    sets = []
    vals = []
    for field in allowed:
        if field in updates and updates[field] is not None:
            sets.append(f"{field} = ?")
            vals.append(updates[field])

    ts = now()
    if sets:
        sets.append("updated_at = ?")
        vals.append(ts)
        vals.append(shipment_id)
        conn.execute(
            f"UPDATE shipments SET {', '.join(sets)} WHERE id = ?", vals
        )

    new_status = updates.get("status")
    if new_status and new_status != old_status:
        conn.execute(
            "INSERT INTO status_history (shipment_id, old_status, new_status, changed_by, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (shipment_id, old_status, new_status, changed_by, status_note, ts),
        )

    conn.commit()
    conn.close()
    return True


def delete_shipment(shipment_id):
    conn = get_db()
    conn.execute("DELETE FROM status_history WHERE shipment_id = ?", (shipment_id,))
    conn.execute("DELETE FROM shipments WHERE id = ?", (shipment_id,))
    conn.commit()
    conn.close()


# --- UI ---
st.title("📦 Treatwell Terminal Shipments")
st.caption("Track terminal shipments to venues")

# --- Sidebar: New Shipment ---
with st.sidebar:
    st.header("New Shipment")
    with st.form("new_shipment_form", clear_on_submit=True):
        new_venue = st.text_input("Venue ID *", placeholder="e.g. 12345")
        new_supplier = st.text_input("Supplier ID *", placeholder="e.g. SUP-001")
        new_address = st.text_area("Shipping Address *", placeholder="Full address")
        new_contact = st.text_input("Contact Name", placeholder="Venue contact")
        new_created_by = st.text_input("Created By", value="Ale")
        new_notes = st.text_area("Notes", placeholder="Any extra info...")
        submitted = st.form_submit_button("Create Shipment", type="primary", use_container_width=True)

        if submitted:
            if not new_venue or not new_supplier or not new_address:
                st.error("Venue ID, Supplier ID, and Address are required.")
            else:
                sid = create_shipment(
                    new_venue.strip(), new_supplier.strip(),
                    new_address.strip(), new_contact.strip(),
                    new_notes.strip(), new_created_by.strip() or "Ale",
                )
                st.success(f"Shipment #{sid} created!")
                st.rerun()

# --- Filter ---
col_filter, col_spacer = st.columns([2, 5])
with col_filter:
    filter_options = ["all"] + STATUS_KEYS
    filter_labels = ["All"] + [STATUS_OPTIONS[k] for k in STATUS_KEYS]
    status_filter = st.selectbox(
        "Filter by status",
        options=filter_options,
        format_func=lambda x: "All" if x == "all" else format_status(x),
    )

# --- Shipments table ---
shipments = get_shipments(status_filter)

if not shipments:
    st.info("No shipments found. Use the sidebar to create one.")
else:
    for s in shipments:
        with st.expander(
            f"**#{s['id']}** — Venue {s['venue_id']} | {format_status(s['status'])} | "
            f"{'Serial: ' + s['serial_number'] if s['serial_number'] else 'No serial yet'} | "
            f"Updated {format_date(s['updated_at'])}",
            expanded=False,
        ):
            # Display current info
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**Venue ID:** {s['venue_id']}")
                st.markdown(f"**Supplier ID:** {s['supplier_id']}")
                st.markdown(f"**Contact:** {s['contact_name'] or '—'}")
            with col2:
                st.markdown(f"**Serial #:** {s['serial_number'] or '—'}")
                st.markdown(f"**Tracking #:** {s['tracking_number'] or '—'}")
                st.markdown(f"**Carrier:** {s['carrier'] or '—'}")
            with col3:
                st.markdown(f"**Status:** {format_status(s['status'])}")
                st.markdown(f"**Assigned To:** {s['assigned_to'] or '—'}")
                st.markdown(f"**Created By:** {s['created_by']}")

            st.markdown(f"**Address:** {s['address']}")
            if s["notes"]:
                st.markdown(f"**Notes:** {s['notes']}")

            st.divider()

            # Edit form
            st.subheader("Update Shipment")
            with st.form(f"edit_{s['id']}"):
                e_col1, e_col2 = st.columns(2)
                with e_col1:
                    e_serial = st.text_input("Serial Number", value=s["serial_number"] or "", key=f"serial_{s['id']}")
                    e_tracking = st.text_input("Tracking Number", value=s["tracking_number"] or "", key=f"tracking_{s['id']}")
                    e_carrier = st.text_input("Carrier", value=s["carrier"] or "", key=f"carrier_{s['id']}", placeholder="DHL, UPS, GLS...")
                with e_col2:
                    e_status = st.selectbox(
                        "Status",
                        options=STATUS_KEYS,
                        index=STATUS_KEYS.index(s["status"]),
                        format_func=format_status,
                        key=f"status_{s['id']}",
                    )
                    e_assigned = st.text_input("Assigned To", value=s["assigned_to"] or "", key=f"assigned_{s['id']}")
                    e_changed_by = st.text_input("Updated By", key=f"changed_by_{s['id']}", placeholder="Your name")

                e_notes = st.text_area("Notes", value=s["notes"] or "", key=f"notes_{s['id']}")
                e_status_note = st.text_input("Status Update Note", key=f"status_note_{s['id']}", placeholder="Reason for status change")

                btn_col1, btn_col2 = st.columns([1, 4])
                with btn_col1:
                    save = st.form_submit_button("Save Changes", type="primary")
                with btn_col2:
                    delete = st.form_submit_button("Delete Shipment")

                if save:
                    update_shipment(
                        s["id"],
                        {
                            "serial_number": e_serial.strip(),
                            "tracking_number": e_tracking.strip(),
                            "carrier": e_carrier.strip(),
                            "status": e_status,
                            "assigned_to": e_assigned.strip(),
                            "notes": e_notes.strip(),
                        },
                        changed_by=e_changed_by.strip(),
                        status_note=e_status_note.strip(),
                    )
                    st.success("Shipment updated!")
                    st.rerun()

                if delete:
                    delete_shipment(s["id"])
                    st.success("Shipment deleted.")
                    st.rerun()

            # Status history
            history = get_history(s["id"])
            if history:
                st.subheader("Status History")
                for h in history:
                    old = format_status(h["old_status"]) if h["old_status"] else ""
                    new = format_status(h["new_status"])
                    arrow = f"{old} → {new}" if old else new
                    by = f" — by {h['changed_by']}" if h["changed_by"] else ""
                    note = f" — {h['note']}" if h["note"] else ""
                    st.caption(f"{format_date(h['created_at'])}  |  {arrow}{by}{note}")
