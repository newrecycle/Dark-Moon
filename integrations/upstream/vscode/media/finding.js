// @ts-check
(function () {
  const vscode = acquireVsCodeApi();
  const app = document.getElementById('app');

  function esc(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function section(title, bodyHtml) {
    if (!bodyHtml) return '';
    return `<h2>${esc(title)}</h2>${bodyHtml}`;
  }

  function list(items) {
    if (!items || !items.length) return '';
    return '<ul>' + items.map((i) => `<li><pre>${esc(i)}</pre></li>`).join('') + '</ul>';
  }

  function render(msg) {
    const f = msg.finding;
    const ev = f.evidence || {};
    const banner = msg.rehydrated
      ? `<div class="banner"><span>⚠ Showing <b>real</b> infrastructure values.</span></div>`
      : `<div class="banner"><span>Sensitive values are redacted.</span>${
          msg.canReveal
            ? `<button id="reveal">Reveal real values (local)</button>`
            : `<span class="muted">Reveal disabled on remote workbench</span>`
        }</div>`;

    app.innerHTML = `
      <h1>${esc(f.title)}</h1>
      <div class="meta">
        <span class="chip ${esc(f.severity)}">${esc(f.severity)}</span>
        ${f.cvss_score != null ? `<span class="badge">CVSS ${esc(f.cvss_score)}</span>` : ''}
        ${f.cve ? `<span class="badge">${esc(f.cve)}</span>` : ''}
        ${f.category ? `<span class="badge">${esc(f.category)}</span>` : ''}
        <span class="badge">${esc(f.status)}</span>
        ${f.discovered_by_agent ? `<span class="badge">agent: ${esc(f.discovered_by_agent)}</span>` : ''}
      </div>
      ${
        f.mitre_attack_id || f.iso27001_control
          ? `<div class="meta">
              ${f.mitre_attack_id ? `<span class="badge">MITRE ${esc(f.mitre_attack_id)}${f.mitre_attack_name ? ' · ' + esc(f.mitre_attack_name) : ''}</span>` : ''}
              ${f.iso27001_control ? `<span class="badge">ISO 27001 ${esc(f.iso27001_control)}</span>` : ''}
            </div>`
          : ''
      }
      ${banner}
      ${section('Description', f.description ? `<p>${esc(f.description)}</p>` : '')}
      ${f.endpoint ? section('Endpoint', `<pre>${esc(f.endpoint)}</pre>`) : ''}
      ${section('Explanation', ev.explanation ? `<p>${esc(ev.explanation)}</p>` : '')}
      ${section('Commands', list(ev.commands))}
      ${section('Payloads', list(ev.payloads))}
      ${ev.raw_request ? section('Request', `<pre>${esc(ev.raw_request)}</pre>`) : ''}
      ${ev.raw_response ? section('Response', `<pre>${esc(ev.raw_response)}</pre>`) : ''}
      ${section('Logs', list(ev.logs))}
      ${
        f.remediation
          ? section('Remediation', `<div class="remediation">${esc(f.remediation)}</div>`)
          : ''
      }
    `;
    const btn = document.getElementById('reveal');
    if (btn) btn.addEventListener('click', () => vscode.postMessage({ type: 'reveal' }));
  }

  window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'finding') render(event.data);
  });
  vscode.postMessage({ type: 'ready' });
})();
