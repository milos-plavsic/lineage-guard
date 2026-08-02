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
  text('review-count', data.summary.reviewBranches);
  text('safe-count', data.summary.safeBranches);
  text('risk-score', data.summary.maxRisk);

  const branches = document.getElementById('branches');
  data.report.decisions.forEach((decision) => {
    const row = element('article', 'branch');
    row.append(element('div', 'branch-name', decision.asset.name));
    row.append(element('div', 'branch-reason', `${decision.evidence_strength.replaceAll('_', ' ')} · ${decision.rationale}`));
    row.append(element('span', `decision ${decision.action}`, decision.action));
    branches.append(row);
  });

  const candidates = document.getElementById('recovery-candidates');
  data.recovery.evaluations.forEach((candidate) => {
    const card = element('article', `candidate ${candidate.verdict}`);
    const heading = element('div', 'candidate-heading');
    heading.append(element('h3', '', candidate.title));
    heading.append(element('span', `verdict ${candidate.verdict}`, candidate.verdict));
    card.append(heading);
    const metrics = element('p', 'candidate-metrics', `Invalid rows ${candidate.before_invalid_rows} → ${candidate.after_invalid_rows} · total ${(candidate.candidate_total_cents / 100).toFixed(2)}`);
    card.append(metrics);
    const checks = element('ul', 'checks');
    candidate.checks.forEach((check) => {
      const item = element('li', check.passed ? 'passed' : 'failed');
      item.append(element('span', '', check.passed ? '✓' : '×'));
      item.append(element('span', '', check.name.replaceAll('_', ' ')));
      checks.append(item);
    });
    card.append(checks);
    candidates.append(card);
  });
  text('certificate-id', data.recovery.certificate.certificate_id);
  text('certificate-transition', data.recovery.certificate.transition.replace('_to_', ' → '));
  text('certificate-hash', `sha256:${data.recovery.certificate.certificate_sha256}`);

  text('genome-id', data.chronos.genome.genome_id);
  text('control-count', data.chronos.genome.prevention_controls.length);
  text('invariant-count', data.chronos.genome.required_invariants.length);
  text('genome-context', `sha256:${data.chronos.genome.context_sha256}`);
  const changes = document.getElementById('change-evaluations');
  data.chronos.evaluations.forEach((evaluation) => {
    const card = element('article', `change-card ${evaluation.decision}`);
    card.append(element('span', 'change-label', evaluation.change.change_id));
    card.append(element('h3', '', evaluation.change.title));
    card.append(element('span', `change-decision ${evaluation.decision}`, evaluation.decision.replaceAll('_', ' ')));
    const failed = evaluation.checks.filter((check) => !check.passed);
    card.append(element('p', '', failed.length ? failed[0].detail : 'Historical failure prevented; context remains valid.'));
    changes.append(card);
  });
  const coverage = document.getElementById('immunity-coverage');
  data.chronos.coverage.forEach((entry) => {
    const row = element('div', 'coverage-row');
    row.append(element('strong', '', entry.asset_name));
    row.append(element('span', `coverage-status ${entry.status}`, entry.status.replaceAll('_', ' ')));
    coverage.append(row);
  });
  const passport = data.chronos.evaluations.find((item) => item.passport);
  text('passport-hash', `sha256:${passport.passport.statement_sha256}`);

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
