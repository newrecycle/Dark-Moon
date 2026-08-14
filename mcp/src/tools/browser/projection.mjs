/** Return only the privacy-safe collector fields requested by a browser mode. */
export function projectPage(page, mode) {
  const base = {
    url: page.url,
    title: page.title,
    depth: page.depth,
    status: page.status,
  };
  if (page.error) return { ...base, error: page.error };

  const fieldsByMode = {
    content: ["text_excerpt", "headings"],
    metadata: ["headings"],
    links: ["links"],
    forms: ["forms"],
    scripts: ["scripts", "event_handlers"],
    dom_sinks: ["scripts", "event_handlers"],
    network: [],
    console: [],
    accessibility: ["accessibility"],
    performance: ["performance"],
    security: ["forms", "scripts", "event_handlers", "security"],
    screenshot: ["headings"],
  };
  const fields = fieldsByMode[mode];
  if (!fields) return page;
  for (const field of fields) base[field] = page[field];
  return base;
}
