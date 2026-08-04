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
  text('metadata-origin', data.provenance.metadata_source.replaceAll('_', ' '));
  text('mutation-state', data.provenance.mutations_applied ? 'applied' : 'not applied');
  text('proof-state', data.provenance.proof_authenticated ? 'authenticated' : 'integrity-valid · unsigned');
  const receipt = data.lineage_read.receipt;
  text('memory-incident', `${data.immune_memory.incident.record_digest.slice(0, 18)}…`);
  text('memory-decision', data.immune_memory.decision.replaceAll('_', ' '));
  text('memory-outcome', `${data.immune_memory.prevention.record_digest.slice(0, 18)}…`);
  text('memory-chain', data.immune_memory.chain_verification.valid
    ? `Verified · ${data.immune_memory.chain_verification.record_count} records`
    : 'Invalid · blocked');
  document.getElementById('evaluate-inherited').addEventListener('click', () => {
    const guardEnabled = document.getElementById('future-guard').value === 'true';
    const evaluation = data.chronos.evaluations.find(
      (item) => item.change.quality_guard_enabled === guardEnabled
        && item.evaluated_context_sha256 === data.chronos.genome.context_sha256,
    );
    text(
      'inherited-result',
      `Agent B verified ${data.immune_memory.incident.record_digest.slice(0, 18)}… → ${evaluation.decision.replaceAll('_', ' ')}. ${evaluation.checks.find((check) => !check.passed)?.detail || 'Historical failure remains prevented.'}`,
    );
  });
  text('read-capability', receipt.capabilities.join(' · ').replaceAll('_', ' ').toLowerCase());
  text('read-source', receipt.readConsistency.source.toLowerCase().replaceAll('_', ' '));
  text('read-completeness', receipt.readConsistency.completeness.toLowerCase());
  text('read-cache', receipt.readConsistency.responseCache.toLowerCase().replaceAll('_', ' '));
  text('read-digest', `${receipt.receiptDigest.slice(0, 20)}…`);
  text('read-limitations', receipt.limitations.join(' · ').replaceAll('_', ' ').toLowerCase());
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

  text('proof-node-count', data.proofgraph.nodes.length);
  text('proof-edge-count', data.proofgraph.edges.length);
  text('causal-cut-count', data.proofgraph.causal_cuts.length);
  text('bundle-valid', data.proof_bundle.authenticated ? 'signed' : 'verified*');
  const decisionSelect = document.getElementById('decision-select');
  const cuts = new Map(data.proofgraph.causal_cuts.map((cut) => [cut.decision_node_id, cut]));
  const nodes = new Map(data.proofgraph.nodes.map((node) => [node.node_id, node]));
  const counterfactuals = new Map(data.proofgraph.counterfactuals.map((item) => [item.evidence_node_id, item]));
  data.proofgraph.nodes.filter((node) => node.kind === 'decision').forEach((node) => {
    const option = element('option', '', node.claim);
    option.value = node.node_id;
    decisionSelect.append(option);
  });
  const renderCut = () => {
    const cut = cuts.get(decisionSelect.value);
    const container = document.getElementById('causal-cut');
    container.replaceChildren();
    cut.evidence_node_ids.forEach((nodeId) => {
      const evidence = nodes.get(nodeId);
      const item = element('article', 'evidence-chip');
      item.append(element('span', '', evidence.kind));
      item.append(element('strong', '', evidence.claim));
      container.append(item);
    });
    const evidenceSelect = document.getElementById('evidence-select');
    evidenceSelect.replaceChildren();
    cut.evidence_node_ids.map((id) => counterfactuals.get(id)).filter(Boolean).forEach((simulation) => {
      const option = element('option', '', nodes.get(simulation.evidence_node_id).claim);
      option.value = simulation.evidence_node_id;
      evidenceSelect.append(option);
    });
    const renderSimulation = () => {
      const simulation = counterfactuals.get(evidenceSelect.value);
      text('counterfactual-explanation', simulation.explanation);
      document.getElementById('simulate-change').dataset.evidenceId = simulation.evidence_node_id;
      text('counterfactual-result', 'Evidence unchanged');
    };
    evidenceSelect.onchange = renderSimulation;
    renderSimulation();
  };
  decisionSelect.addEventListener('change', renderCut);
  document.getElementById('simulate-change').addEventListener('click', (event) => {
    const simulation = counterfactuals.get(event.currentTarget.dataset.evidenceId);
    text('counterfactual-result', `${simulation.original_action.replaceAll('_', ' ')} → ${simulation.resulting_action.replaceAll('_', ' ')}`);
  });
  renderCut();
  const gaps = document.getElementById('evidence-gaps');
  data.proofgraph.evidence_gaps.forEach((gap) => {
    const item = element('article', 'gap-card');
    item.append(element('strong', 'gap-score', `${gap.priority_score}/100`));
    const detail = element('div');
    detail.append(element('h4', '', gap.title));
    detail.append(element('p', '', gap.recommended_action));
    item.append(detail);
    gaps.append(item);
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
