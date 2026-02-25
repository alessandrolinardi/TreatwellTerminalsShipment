import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- Page config ---
st.set_page_config(
    page_title="Treatwell Terminal Shipments",
    page_icon="📦",
    layout="wide",
)

# --- Google Sheets setup ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHIPMENT_COLS = [
    "id", "venue_id", "supplier_id", "address", "contact_name",
    "serial_number", "tracking_number", "carrier", "status",
    "notes", "created_by", "assigned_to", "created_at", "updated_at",
]

HISTORY_COLS = [
    "id", "shipment_id", "old_status", "new_status",
    "changed_by", "note", "created_at",
]


@st.cache_resource
def get_gsheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(st.secrets["spreadsheet_id"])
    # Ensure worksheets exist with headers
    _ensure_worksheet(sheet, "shipments", SHIPMENT_COLS)
    _ensure_worksheet(sheet, "history", HISTORY_COLS)
    return sheet


def _ensure_worksheet(sheet, title, headers):
    try:
        ws = sheet.worksheet(title)
        if not ws.row_values(1):
            ws.append_row(headers, value_input_option="RAW")
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        ws.append_row(headers, value_input_option="RAW")


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _next_id(ws):
    """Get next auto-increment ID from a worksheet."""
    records = ws.get_all_records()
    if not records:
        return 1
    return max(int(r.get("id", 0)) for r in records) + 1


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
        dt = datetime.fromisoformat(str(date_str))
        return dt.strftime("%d %b %Y %H:%M")
    except (ValueError, TypeError):
        return str(date_str)


# --- DB helpers (Google Sheets) ---
def get_shipments(status_filter="all", search="", date_from=None, date_to=None):
    sheet = get_gsheet()
    ws = sheet.worksheet("shipments")
    records = ws.get_all_records()

    results = []
    search_lower = search.lower() if search else ""

    for r in records:
        # Status filter
        if status_filter and status_filter != "all" and r.get("status") != status_filter:
            continue

        # Text search across multiple fields
        if search_lower:
            searchable = " ".join(
                str(r.get(f, "")).lower()
                for f in ["venue_id", "supplier_id", "serial_number",
                          "tracking_number", "contact_name"]
            )
            if search_lower not in searchable:
                continue

        # Date filters
        created = str(r.get("created_at", ""))[:10]
        if date_from and created < date_from.strftime("%Y-%m-%d"):
            continue
        if date_to and created > date_to.strftime("%Y-%m-%d"):
            continue

        results.append(r)

    # Sort by updated_at descending
    results.sort(key=lambda x: str(x.get("updated_at", "")), reverse=True)
    return results


def get_history(shipment_id):
    sheet = get_gsheet()
    ws = sheet.worksheet("history")
    records = ws.get_all_records()
    results = [r for r in records if str(r.get("shipment_id")) == str(shipment_id)]
    results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return results


def create_shipment(venue_id, supplier_id, address, contact_name, notes, created_by):
    sheet = get_gsheet()
    ws_ship = sheet.worksheet("shipments")
    ws_hist = sheet.worksheet("history")

    ts = now()
    ship_id = _next_id(ws_ship)

    ws_ship.append_row(
        [ship_id, venue_id, supplier_id, address, contact_name,
         "", "", "", "pending", notes, created_by, "", ts, ts],
        value_input_option="RAW",
    )

    hist_id = _next_id(ws_hist)
    ws_hist.append_row(
        [hist_id, ship_id, "", "pending", created_by, "Shipment created", ts],
        value_input_option="RAW",
    )

    return ship_id


def _find_row(ws, shipment_id):
    """Find the row number (1-indexed) for a shipment by ID. Row 1 is headers."""
    records = ws.get_all_records()
    for i, r in enumerate(records):
        if str(r.get("id")) == str(shipment_id):
            return i + 2, r  # +2: 1 for 0-index, 1 for header row
    return None, None


def update_shipment(shipment_id, updates, changed_by="", status_note=""):
    sheet = get_gsheet()
    ws = sheet.worksheet("shipments")

    row_num, old = _find_row(ws, shipment_id)
    if not old:
        return False

    old_status = old.get("status", "")
    ts = now()

    allowed = [
        "venue_id", "supplier_id", "address", "contact_name",
        "serial_number", "tracking_number", "carrier",
        "status", "notes", "assigned_to",
    ]

    # Build updated row
    updated = dict(old)
    for field in allowed:
        if field in updates and updates[field] is not None:
            updated[field] = updates[field]
    updated["updated_at"] = ts

    # Write back the full row
    row_values = [updated.get(col, "") for col in SHIPMENT_COLS]
    ws.update(f"A{row_num}:{chr(64 + len(SHIPMENT_COLS))}{row_num}", [row_values],
              value_input_option="RAW")

    # Log status change
    new_status = updates.get("status")
    if new_status and new_status != old_status:
        ws_hist = sheet.worksheet("history")
        hist_id = _next_id(ws_hist)
        ws_hist.append_row(
            [hist_id, shipment_id, old_status, new_status,
             changed_by, status_note, ts],
            value_input_option="RAW",
        )

    return True


def delete_shipment(shipment_id):
    sheet = get_gsheet()

    # Delete from shipments
    ws = sheet.worksheet("shipments")
    row_num, _ = _find_row(ws, shipment_id)
    if row_num:
        ws.delete_rows(row_num)

    # Delete related history rows (bottom-up to keep indices stable)
    ws_hist = sheet.worksheet("history")
    records = ws_hist.get_all_records()
    rows_to_delete = []
    for i, r in enumerate(records):
        if str(r.get("shipment_id")) == str(shipment_id):
            rows_to_delete.append(i + 2)  # +2 for 0-index + header

    for row_num in sorted(rows_to_delete, reverse=True):
        ws_hist.delete_rows(row_num)


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
            f"{'Serial: ' + str(s['serial_number']) if s['serial_number'] else 'No serial yet'} | "
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
                    e_serial = st.text_input("Serial Number", value=str(s["serial_number"] or ""), key=f"serial_{s['id']}")
                    e_tracking = st.text_input("Tracking Number", value=str(s["tracking_number"] or ""), key=f"tracking_{s['id']}")
                    e_carrier = st.text_input("Carrier", value=str(s["carrier"] or ""), key=f"carrier_{s['id']}", placeholder="DHL, UPS, GLS...")
                with e_col2:
                    current_status = s["status"] if s["status"] in STATUS_KEYS else "pending"
                    e_status = st.selectbox(
                        "Status",
                        options=STATUS_KEYS,
                        index=STATUS_KEYS.index(current_status),
                        format_func=format_status,
                        key=f"status_{s['id']}",
                    )
                    e_assigned = st.text_input("Assigned To", value=str(s["assigned_to"] or ""), key=f"assigned_{s['id']}")
                    e_changed_by = st.text_input("Updated By", key=f"changed_by_{s['id']}", placeholder="Your name")

                e_notes = st.text_area("Notes", value=str(s["notes"] or ""), key=f"notes_{s['id']}")
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
