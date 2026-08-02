const text = (id, value) => { document.getElementById(id).textContent = value; };
const element = (tag, className, content) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
};

async function loadIncident() {
  let response = await fetch('api/incidents/current', { headers: { Accept: 'application/json' } });
  if (!response.ok) response = await fetch('incident.json', { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`Incident service returned ${response.status}`);
  const data = await response.json();
  text('incident-id', data.report.incident_id);
  text('overall-status', data.summary.status);
  text('affected-count', data.summary.affectedBranches);
  text('safe-count', data.summary.safeBranches);
  text('risk-score', data.summary.maxRisk);

  const branches = document.getElementById('branches');
  data.report.decisions.forEach((decision) => {
    const row = element('article', 'branch');
    row.append(element('div', 'branch-name', decision.asset.name));
    row.append(element('div', 'branch-reason', decision.rationale));
    row.append(element('span', `decision ${decision.action}`, decision.action));
    branches.append(row);
  });

  const timeline = document.getElementById('timeline');
  data.timeline.forEach((event) => {
    const item = element('li');
    item.append(element('strong', '', event.stage));
    item.append(element('span', '', event.detail));
    timeline.append(item);
  });

  const artifacts = document.getElementById('artifacts');
  data.artifacts.forEach((artifact) => {
    const item = element('li');
    item.append(element('strong', '', artifact.relative_path));
    item.append(element('code', '', `sha256:${artifact.sha256}`));
    artifacts.append(item);
  });
}

loadIncident().catch((error) => {
  const alert = document.getElementById('error');
  alert.textContent = `Unable to load incident evidence. ${error.message}`;
  alert.hidden = false;
});
