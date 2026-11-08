(() => {
  const controls = document.getElementById('controls');
  const search = document.getElementById('search');
  const filter = document.getElementById('filter');
  const rows = Array.from(document.querySelectorAll('tr[data-route]'));
  const shown = document.getElementById('shown');
  const update = () => {
    const query = search.value.trim().toLocaleLowerCase();
    let count = 0;
    rows.forEach(row => {
      const matches = filter.value === 'all' || (filter.value === 'warnings' ? row.dataset.warnings === 'true' : row.dataset.route === filter.value);
      row.hidden = !matches || !row.textContent.toLocaleLowerCase().includes(query);
      if (!row.hidden) count++;
    });
    shown.textContent = `Showing ${count} of ${rows.length} source rows`;
    document.getElementById('no-matches').hidden = count !== 0;
  };
  controls.hidden = false;
  search.addEventListener('input', update);
  filter.addEventListener('change', update);
  update();
})();
