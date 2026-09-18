const fs = require('fs');
const path = 'workflows/01-telegram-content-pipeline-orm.json';
const workflow = JSON.parse(fs.readFileSync(path, 'utf8'));
const nodes = workflow.nodes;
const connections = workflow.connections;
const byName = (name) => nodes.find((node) => node.name === name);

const existing = byName('ORM: Read completed candidate');
const node = {
  parameters: {
    method: 'GET',
    url: "={{ ($env.CONTENT_STORE_BASE_URL || 'http://content-store:8080') + '/v1/candidates/' + $json.id }}",
    options: { timeout: 30000 },
  },
  id: 'f1c2d3e4-7a86-4c2f-9d0a-5b1e4f75a510',
  name: 'ORM: Read completed candidate',
  type: 'n8n-nodes-base.httpRequest',
  typeVersion: 4.2,
  position: [5680, 0],
};
if (existing) Object.assign(existing, node);
else nodes.push(node);

const prepare = byName('Prepare ORM result');
prepare.parameters.jsCode = "const candidateId = Number($json.id || $json.candidate_id || 0);\nreturn { json: { ...$json, candidate_id: candidateId } };";

connections['ORM: Complete candidate'] = {
  main: [
    [{ node: 'ORM: Read completed candidate', type: 'main', index: 0 }],
    [{ node: 'ORM: Mark candidate failed', type: 'main', index: 0 }],
  ],
};
connections['ORM: Read completed candidate'] = {
  main: [[{ node: 'Prepare ORM result', type: 'main', index: 0 }]],
};

workflow.versionId = 'a1b2c3d4-7e86-4c2f-9d0a-5b1e4f75a510';
workflow.versionCounter = Number(workflow.versionCounter || 1) + 1;
fs.writeFileSync(path, JSON.stringify(workflow, null, 2) + '\n');
