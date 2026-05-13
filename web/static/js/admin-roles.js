function toggleAll(btn) {
    const form = btn.closest('form');
    const boxes = form.querySelectorAll('input[type=checkbox]');
    const allChecked = [...boxes].every(b => b.checked);
    boxes.forEach(b => b.checked = !allChecked);
}

function openEditModal(roleId, displayName, description) {
    document.getElementById('edit-modal-form').action = '/admin/roles/' + roleId + '/edit';
    document.getElementById('edit-display-name').value = displayName;
    document.getElementById('edit-description').value = description || '';
    document.getElementById('edit-modal').classList.add('open');
}

function closeEditModal() {
    document.getElementById('edit-modal').classList.remove('open');
}

document.getElementById('edit-modal').addEventListener('click', function(e) {
    if (e.target === this) closeEditModal();
});
