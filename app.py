import streamlit as st
import psycopg2
import psycopg2.extras
from datetime import datetime

# --- Page config ---
st.set_page_config(
    page_title="Treatwell Terminal Shipments",
    page_icon="📦",
    layout="wide",
)

# --- Database setup (Supabase PostgreSQL) ---


def get_db():
    return psycopg2.connect(st.secrets["database_url"])


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS status_history (
            id SERIAL PRIMARY KEY,
            shipment_id INTEGER NOT NULL REFERENCES shipments(id),
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_by TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    cur.close()
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
def get_shipments(status_filter="all", search="", date_from=None, date_to=None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    clauses = []
    params = []

    if status_filter and status_filter != "all":
        clauses.append("status = %s")
        params.append(status_filter)

    if search:
        clauses.append(
            "(venue_id ILIKE %s OR supplier_id ILIKE %s OR serial_number ILIKE %s "
            "OR tracking_number ILIKE %s OR contact_name ILIKE %s)"
        )
        term = f"%{search}%"
        params.extend([term] * 5)

    if date_from:
        clauses.append("created_at::date >= %s")
        params.append(date_from.strftime("%Y-%m-%d"))

    if date_to:
        clauses.append("created_at::date <= %s")
        params.append(date_to.strftime("%Y-%m-%d"))

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    cur.execute(
        f"SELECT * FROM shipments{where} ORDER BY updated_at DESC", params
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_shipment(shipment_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM shipments WHERE id = %s", (shipment_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def get_history(shipment_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM status_history WHERE shipment_id = %s ORDER BY created_at DESC",
        (shipment_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def create_shipment(venue_id, supplier_id, address, contact_name, notes, created_by):
    conn = get_db()
    cur = conn.cursor()
    ts = now()
    cur.execute(
        """INSERT INTO shipments (venue_id, supplier_id, address, contact_name, notes, created_by, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (venue_id, supplier_id, address, contact_name, notes, created_by, ts, ts),
    )
    shipment_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO status_history (shipment_id, new_status, changed_by, note, created_at) VALUES (%s, %s, %s, %s, %s)",
        (shipment_id, "pending", created_by, "Shipment created", ts),
    )
    conn.commit()
    cur.close()
    conn.close()
    return shipment_id


def update_shipment(shipment_id, updates, changed_by="", status_note=""):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM shipments WHERE id = %s", (shipment_id,))
    old = cur.fetchone()
    if not old:
        cur.close()
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
            sets.append(f"{field} = %s")
            vals.append(updates[field])

    ts = now()
    if sets:
        sets.append("updated_at = %s")
        vals.append(ts)
        vals.append(shipment_id)
        cur.execute(
            f"UPDATE shipments SET {', '.join(sets)} WHERE id = %s", vals
        )

    new_status = updates.get("status")
    if new_status and new_status != old_status:
        cur.execute(
            "INSERT INTO status_history (shipment_id, old_status, new_status, changed_by, note, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (shipment_id, old_status, new_status, changed_by, status_note, ts),
        )

    conn.commit()
    cur.close()
    conn.close()
    return True


def delete_shipment(shipment_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM status_history WHERE shipment_id = %s", (shipment_id,))
    cur.execute("DELETE FROM shipments WHERE id = %s", (shipment_id,))
    conn.commit()
    cur.close()
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

# --- Search & Filters ---
search_col, status_col, date_from_col, date_to_col = st.columns([3, 2, 2, 2])
with search_col:
    search_query = st.text_input(
        "Search",
        placeholder="Venue ID, Supplier ID, Serial #, Tracking #, Contact...",
    )
with status_col:
    status_filter = st.selectbox(
        "Status",
        options=["all"] + STATUS_KEYS,
        format_func=lambda x: "All" if x == "all" else format_status(x),
    )
with date_from_col:
    date_from = st.date_input("Created from", value=None)
with date_to_col:
    date_to = st.date_input("Created to", value=None)

# --- Shipments table ---
shipments = get_shipments(status_filter, search_query.strip(), date_from, date_to)

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
