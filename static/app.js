const toggleButton = document.getElementById('toggle-edit');
if (toggleButton) {
  toggleButton.addEventListener('click', () => {
    document.body.classList.toggle('edit-on');
    const isOn = document.body.classList.contains('edit-on');
    toggleButton.textContent = isOn ? 'Disable Edit Mode' : 'Enable Edit Mode';
  });
}

const deleteDialog = document.getElementById('delete-dialog');
const deleteTitle = document.getElementById('delete-title');
const deleteForm = document.getElementById('delete-form');
const deleteCancel = document.getElementById('delete-cancel');

if (deleteDialog && deleteForm && deleteTitle) {
  document.querySelectorAll('.delete-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.id;
      const name = btn.dataset.name || 'component';

      deleteTitle.textContent = `Component: ${name}`;
      deleteForm.action = `/delete/${id}`;
      deleteForm.querySelector('textarea[name="delete_reason"]').value = '';
      deleteDialog.showModal();
    });
  });

  deleteCancel?.addEventListener('click', () => deleteDialog.close());
}
