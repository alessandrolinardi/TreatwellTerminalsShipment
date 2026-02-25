const API = '/api/shipments';

const statusLabels = {
  pending: 'Pending',
  label_created: 'Label Created',
  picked_up: 'Picked Up',
  in_transit: 'In Transit',
  delivered: 'Delivered',
  issue: 'Issue',
};

// --- Load shipments ---
async function loadShipments() {
  const filter = document.getElementById('statusFilter').value;
  const res = await fetch(`${API}?status=${filter}`);
  const shipments = await res.json();
  renderTable(shipments);
}

function renderTable(shipments) {
  const tbody = document.getElementById('shipmentsBody');
  const empty = document.getElementById('emptyState');

  if (shipments.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }

  empty.style.display = 'none';
  tbody.innerHTML = shipments.map(s => `
    <tr onclick="openEdit(${s.id})" style="cursor:pointer;">
      <td>${s.id}</td>
      <td>${esc(s.venue_id)}</td>
      <td>${esc(s.supplier_id)}</td>
      <td title="${esc(s.address)}">${esc(s.address)}</td>
      <td>${esc(s.serial_number) || '<span style="color:#bbb">—</span>'}</td>
      <td>${esc(s.tracking_number) || '<span style="color:#bbb">—</span>'}</td>
      <td>${esc(s.carrier) || '<span style="color:#bbb">—</span>'}</td>
      <td><span class="badge badge-${s.status}">${statusLabels[s.status] || s.status}</span></td>
      <td>${esc(s.assigned_to) || '<span style="color:#bbb">—</span>'}</td>
      <td title="${s.updated_at}">${formatDate(s.updated_at)}</td>
      <td><button class="btn btn-small btn-secondary" onclick="event.stopPropagation(); openEdit(${s.id})">Edit</button></td>
    </tr>
  `).join('');
}

function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr + 'Z');
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

// --- New Shipment ---
document.getElementById('btnNewShipment').addEventListener('click', () => {
  document.getElementById('formNewShipment').reset();
  document.getElementById('newCreatedBy').value = 'Ale';
  openModal('modalNewShipment');
});

document.getElementById('formNewShipment').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    venue_id: document.getElementById('newVenueId').value.trim(),
    supplier_id: document.getElementById('newSupplierId').value.trim(),
    address: document.getElementById('newAddress').value.trim(),
    contact_name: document.getElementById('newContactName').value.trim(),
    created_by: document.getElementById('newCreatedBy').value.trim(),
    notes: document.getElementById('newNotes').value.trim(),
  };
  const res = await fetch(API, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    closeModal('modalNewShipment');
    loadShipments();
  } else {
    const err = await res.json();
    alert(err.error || 'Failed to create shipment');
  }
});

// --- Edit Shipment ---
let currentEditId = null;

async function openEdit(id) {
  currentEditId = id;
  const res = await fetch(`${API}/${id}`);
  if (!res.ok) return alert('Shipment not found');
  const s = await res.json();

  document.getElementById('editShipmentId').textContent = s.id;
  document.getElementById('editVenueId').value = s.venue_id;
  document.getElementById('editSupplierId').value = s.supplier_id;
  document.getElementById('editAddress').value = s.address;
  document.getElementById('editContactName').value = s.contact_name || '';
  document.getElementById('editSerialNumber').value = s.serial_number || '';
  document.getElementById('editTrackingNumber').value = s.tracking_number || '';
  document.getElementById('editCarrier').value = s.carrier || '';
  document.getElementById('editAssignedTo').value = s.assigned_to || '';
  document.getElementById('editStatus').value = s.status;
  document.getElementById('editNotes').value = s.notes || '';
  document.getElementById('editChangedBy').value = '';
  document.getElementById('editStatusNote').value = '';

  // Render history
  const historyDiv = document.getElementById('statusHistory');
  if (s.history && s.history.length > 0) {
    historyDiv.innerHTML = s.history.map(h => `
      <div class="history-item">
        <span class="time">${formatDate(h.created_at)}</span>
        <span class="detail">
          ${h.old_status ? `<span class="badge badge-${h.old_status}" style="font-size:0.65rem;">${statusLabels[h.old_status] || h.old_status}</span> → ` : ''}
          <span class="badge badge-${h.new_status}" style="font-size:0.65rem;">${statusLabels[h.new_status] || h.new_status}</span>
          ${h.note ? ` — ${esc(h.note)}` : ''}
        </span>
        ${h.changed_by ? `<span class="by">by ${esc(h.changed_by)}</span>` : ''}
      </div>
    `).join('');
  } else {
    historyDiv.innerHTML = '<p style="color:#aaa;font-size:0.85rem;">No history yet.</p>';
  }

  openModal('modalEditShipment');
}

document.getElementById('formEditShipment').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    venue_id: document.getElementById('editVenueId').value.trim(),
    supplier_id: document.getElementById('editSupplierId').value.trim(),
    address: document.getElementById('editAddress').value.trim(),
    contact_name: document.getElementById('editContactName').value.trim(),
    serial_number: document.getElementById('editSerialNumber').value.trim(),
    tracking_number: document.getElementById('editTrackingNumber').value.trim(),
    carrier: document.getElementById('editCarrier').value.trim(),
    assigned_to: document.getElementById('editAssignedTo').value.trim(),
    status: document.getElementById('editStatus').value,
    notes: document.getElementById('editNotes').value.trim(),
    changed_by: document.getElementById('editChangedBy').value.trim(),
    status_note: document.getElementById('editStatusNote').value.trim(),
  };

  const res = await fetch(`${API}/${currentEditId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (res.ok) {
    closeModal('modalEditShipment');
    loadShipments();
  } else {
    const err = await res.json();
    alert(err.error || 'Failed to update shipment');
  }
});

document.getElementById('btnDeleteShipment').addEventListener('click', async () => {
  if (!confirm('Are you sure you want to delete this shipment?')) return;
  const res = await fetch(`${API}/${currentEditId}`, { method: 'DELETE' });
  if (res.ok) {
    closeModal('modalEditShipment');
    loadShipments();
  }
});

// --- Modal helpers ---
function openModal(id) {
  document.getElementById(id).style.display = 'flex';
}

function closeModal(id) {
  document.getElementById(id).style.display = 'none';
}

// Close modals on backdrop click
document.querySelectorAll('.modal').forEach(modal => {
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.style.display = 'none';
  });
});

// --- Filter ---
document.getElementById('statusFilter').addEventListener('change', loadShipments);

// --- Init ---
loadShipments();
