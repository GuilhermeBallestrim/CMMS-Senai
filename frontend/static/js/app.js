document.addEventListener('DOMContentLoaded', () => {
  const toast = document.querySelector('[data-toast]');
  let toastTimer;
  const announce = (message) => {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('toast--visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('toast--visible'), 2600);
  };

  if (toast?.dataset.notice) announce(toast.dataset.notice);

  document.querySelectorAll('[data-menu-toggle]').forEach((button) => button.addEventListener('click', () => {
    document.querySelector('.sidebar')?.classList.toggle('sidebar--open');
  }));

  document.querySelectorAll('[data-action]').forEach((button) => button.addEventListener('click', () => announce(button.dataset.action)));

  document.querySelectorAll('[data-password-toggle]').forEach((button) => button.addEventListener('click', () => {
    const input = button.parentElement.querySelector('input');
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
    button.setAttribute('aria-label', input.type === 'password' ? 'Mostrar senha' : 'Ocultar senha');
  }));

  document.querySelectorAll('[data-tab]').forEach((tab) => tab.addEventListener('click', () => {
    const group = tab.closest('main') || document;
    group.querySelectorAll('[data-tab]').forEach((item) => item.classList.toggle('tabs__item--active', item === tab));
    group.querySelectorAll('[data-panel]').forEach((panel) => { panel.hidden = panel.dataset.panel !== tab.dataset.tab; });
  }));

  const filterTable = () => {
    const query = document.querySelector('[data-table-search]')?.value.trim().toLocaleLowerCase('pt-BR') || '';
    const filters = [...document.querySelectorAll('[data-table-filter]')];
    document.querySelectorAll('[data-filter-table tbody tr], .panel--table tbody tr').forEach((row) => {
      const queryMatches = row.textContent.toLocaleLowerCase('pt-BR').includes(query);
      const filtersMatch = filters.every((filter) => !filter.value || row.dataset[filter.dataset.tableFilter] === filter.value);
      row.hidden = !(queryMatches && filtersMatch);
    });
  };
  document.querySelectorAll('[data-table-search], [data-table-filter]').forEach((control) => control.addEventListener('input', filterTable));
  document.querySelectorAll('[data-table-filter]').forEach((control) => control.addEventListener('change', filterTable));

});
