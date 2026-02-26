import streamlit as st
from supabase import create_client
from datetime import datetime, timezone

# --- Page config ---
st.set_page_config(
    page_title="Treatwell Terminal Shipments",
    page_icon="📦",
    layout="wide",
)

# --- Supabase client ---


@st.cache_resource
def get_supabase():
    return create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])


supabase = get_supabase()


def now():
    return datetime.now(timezone.utc).isoformat()


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
    query = supabase.table("shipments").select("*")

    if status_filter and status_filter != "all":
        query = query.eq("status", status_filter)

    if search:
        term = f"%{search}%"
        query = query.or_(
            f"venue_id.ilike.{term},"
            f"supplier_id.ilike.{term},"
            f"serial_number.ilike.{term},"
            f"tracking_number.ilike.{term},"
            f"contact_name.ilike.{term}"
        )

    if date_from:
        query = query.gte("created_at", f"{date_from.strftime('%Y-%m-%d')}T00:00:00")

    if date_to:
        query = query.lte("created_at", f"{date_to.strftime('%Y-%m-%d')}T23:59:59")

    response = query.order("updated_at", desc=True).execute()
    return response.data


def get_shipment(shipment_id):
    response = (
        supabase.table("shipments")
        .select("*")
        .eq("id", shipment_id)
        .maybe_single()
        .execute()
    )
    return response.data


def get_history(shipment_id):
    response = (
        supabase.table("status_history")
        .select("*")
        .eq("shipment_id", shipment_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


def create_shipment(venue_id, supplier_id, address, contact_name, notes, created_by):
    ts = now()
    response = (
        supabase.table("shipments")
        .insert(
            {
                "venue_id": venue_id,
                "supplier_id": supplier_id,
                "address": address,
                "contact_name": contact_name,
                "notes": notes,
                "created_by": created_by,
                "created_at": ts,
                "updated_at": ts,
            }
        )
        .execute()
    )
    shipment_id = response.data[0]["id"]

    supabase.table("status_history").insert(
        {
            "shipment_id": shipment_id,
            "new_status": "pending",
            "changed_by": created_by,
            "note": "Shipment created",
            "created_at": ts,
        }
    ).execute()

    return shipment_id


def update_shipment(shipment_id, updates, changed_by="", status_note=""):
    old = get_shipment(shipment_id)
    if not old:
        return False

    old_status = old["status"]
    allowed = [
        "venue_id", "supplier_id", "address", "contact_name",
        "serial_number", "tracking_number", "carrier",
        "status", "notes", "assigned_to",
    ]
    changes = {k: v for k, v in updates.items() if k in allowed and v is not None}

    ts = now()
    if changes:
        changes["updated_at"] = ts
        supabase.table("shipments").update(changes).eq("id", shipment_id).execute()

    new_status = updates.get("status")
    if new_status and new_status != old_status:
        supabase.table("status_history").insert(
            {
                "shipment_id": shipment_id,
                "old_status": old_status,
                "new_status": new_status,
                "changed_by": changed_by,
                "note": status_note,
                "created_at": ts,
            }
        ).execute()

    return True


def delete_shipment(shipment_id):
    supabase.table("status_history").delete().eq("shipment_id", shipment_id).execute()
    supabase.table("shipments").delete().eq("id", shipment_id).execute()


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
