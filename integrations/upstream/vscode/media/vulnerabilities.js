// @ts-check
(function () {
  const vscode = acquireVsCodeApi();
  const $ = (id) => document.getElementById(id);
  const state = {
    rows: [],
    sortKey: 'severityRank',
    sortAsc: true,
    search: '',
    sev: '',
    status: '',
    error: undefined,
    loading: false,
  };

  function esc(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function filtered() {
    let rows = state.rows;
    if (state.sev) rows = rows.filter((r) => r.severity === state.sev);
    if (state.status) rows = rows.filter((r) => r.status === state.status);
    if (state.search) {
      const q = state.search.toLowerCase();
      rows = rows.filter((r) =>
        [r.title, r.category, r.component, r.campaign, r.status]
          .join(' ')
          .toLowerCase()
          .includes(q)
      );
    }
    const k = state.sortKey;
    const dir = state.sortAsc ? 1 : -1;
    return [...rows].sort((a, b) => {
      let av = a[k];
      let bv = b[k];
      if (typeof av === 'string') av = av.toLowerCase();
      if (typeof bv === 'string') bv = bv.toLowerCase();
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }

  function render() {
    const tbody = $('rows');
    const empty = $('empty');
    const count = $('count');
    if (state.error) {
      tbody.innerHTML = '';
      empty.hidden = false;
      empty.textContent = 'Not available: ' + state.error;
      count.textContent = '';
      return;
    }
    const rows = filtered();
    count.textContent =
      rows.length + ' of ' + state.rows.length + ' findings' +
      (state.loading ? ' (loading…)' : '');
    if (rows.length === 0) {
      tbody.innerHTML = '';
      empty.hidden = false;
      empty.textContent = state.rows.length
        ? 'No findings match the current filters.'
        : (state.loading ? 'Loading…' : 'No findings yet.');
      return;
    }
    empty.hidden = true;
    tbody.innerHTML = rows
      .map(
        (r) => `<tr data-id="${esc(r.id)}" tabindex="0">
        <td><span class="chip ${esc(r.severity)}">${esc(r.severity)}</span>${
          r.cvss != null ? ` <span class="type">${esc(r.cvss)}</span>` : ''
        }</td>
        <td><div class="title">${esc(r.title)}</div><div class="type">${esc(
          r.category
        )}</div></td>
        <td class="component">${esc(r.component)}</td>
        <td>${esc(r.status)}</td>
        <td class="campaign">${esc(r.campaign)}</td>
      </tr>`
      )
      .join('');
    for (const tr of tbody.querySelectorAll('tr')) {
      const open = () => vscode.postMessage({ type: 'open', id: tr.dataset.id });
      tr.addEventListener('click', open);
      tr.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') open();
      });
    }
    for (const th of document.querySelectorAll('th')) {
      th.classList.toggle('sorted', th.dataset.sort === state.sortKey);
      th.classList.toggle('asc', th.dataset.sort === state.sortKey && state.sortAsc);
    }
  }

  $('search').addEventListener('input', (e) => {
    state.search = e.target.value;
    render();
  });
  $('sev').addEventListener('change', (e) => {
    state.sev = e.target.value;
    render();
  });
  $('status').addEventListener('change', (e) => {
    state.status = e.target.value;
    render();
  });
  for (const th of document.querySelectorAll('th')) {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) state.sortAsc = !state.sortAsc;
      else {
        state.sortKey = key;
        state.sortAsc = true;
      }
      render();
    });
  }

  window.addEventListener('message', (event) => {
    const msg = event.data;
    if (msg.type === 'rows') {
      state.rows = msg.rows || [];
      state.error = msg.error;
      state.loading = !!msg.loading;
      render();
    }
  });

  vscode.postMessage({ type: 'ready' });
})();
