import { describe, expect, it } from 'vitest';
import yaml from 'js-yaml';
import type { Edge, Node } from '@xyflow/react';
import { NODE_TYPES } from '@app/constants/workflow-builder';
import { applyGraphAction } from './graphUtils';
import { parseYamlToGraph, serializeGraphToYaml } from './yamlSync';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Doc = any;

const load = (text: string): Doc => yaml.load(text);

const parseOk = (text: string) => {
  const parsed = parseYamlToGraph(text);
  if (parsed.error) throw new Error(`parse failed: ${parsed.error}`);
  return parsed;
};

const serializeOk = (nodes: Node[], edges: Edge[], text: string) => {
  const result = serializeGraphToYaml(nodes, edges, text);
  if (!result.ok) throw new Error(`serialize failed: ${result.error}`);
  return result;
};

const roundTrip = (text: string) => {
  const parsed = parseOk(text);
  const result = serializeOk(parsed.nodes, parsed.edges, text);
  return { parsed, result, before: load(text), after: load(result.yaml) };
};

// Every node name the workflow document refers to (start, edges, end, routing, input_filter, execute_node)
const referencedNames = (doc: Doc): string[] => {
  const arium = doc.arium ?? {};
  const names: string[] = [];
  const workflow = arium.workflow ?? {};
  if (workflow.start) names.push(workflow.start);
  (workflow.edges ?? []).forEach((e: Doc) => {
    names.push(e.from);
    if (e.router) names.push(e.router);
    names.push(...(Array.isArray(e.to) ? e.to : [e.to]));
  });
  names.push(...(workflow.end ?? []));
  (arium.routers ?? []).forEach((r: Doc) => {
    names.push(...Object.keys(r.routing_options ?? {}));
    names.push(...Object.values<string>(r.routes ?? {}));
    if (r.default) names.push(r.default);
    names.push(...(r.flow_pattern ?? []));
  });
  ['agents', 'function_nodes', 'iterators', 'foreach_nodes', 'ariums'].forEach((key) => {
    (arium[key] ?? []).forEach((entry: Doc) => {
      names.push(...(entry.input_filter ?? []));
      if (entry.execute_node) names.push(entry.execute_node);
    });
  });
  return names;
};

const agentNames = (doc: Doc): string[] => (doc.arium.agents ?? []).map((a: Doc) => a.name);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

// Copy of defaultYamlContent in src/pages/apps/[appId]/workflows/CreateWorkflowDialog.tsx (not exported there)
const DEFAULT_YAML = `metadata:
  name: content-creation-yaml-workflow
  version: 1.0.0
  description: "Content creation with YAML-defined smart router"

arium:
  agents:
    - name: content_creator
      role: "Content Creator"
      job: "Create initial content drafts on any topic with engaging style."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.7

    - name: technical_writer
      role: "Technical Writer"
      job: "Specialize in technical documentation, tutorials, and educational content."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3

    - name: creative_writer
      role: "Creative Writer"
      job: "Specialize in creative writing, storytelling, and marketing content."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.8

    - name: editor
      role: "Content Editor"
      job: "Review and polish content for clarity, flow, and quality."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2

  # Router definitions in YAML
  routers:
    - name: content_router
      type: smart
      routing_options:
        technical_writer: "Handle technical documentation, tutorials, how-to guides, and educational content"
        creative_writer: "Handle creative writing, marketing copy, stories, and engaging content"
        editor: "Move to editing when content is ready for review and polishing"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        context_description: "a content creation workflow that routes based on content type and readiness"
        fallback_strategy: "first"

  workflow:
    start: content_creator
    edges:
      - from: content_creator
        to: [technical_writer, creative_writer, editor]
        router: content_router
      - from: technical_writer
        to: [editor]
      - from: creative_writer
        to: [editor]
    end: [editor]
`;

const STORED_AGENT_YAML = `arium:
  agents:
    - name: ns/agent
  workflow:
    start: ns/agent
    edges: []
    end: [ns/agent]
`;

const YAML_FILE_AGENT_YAML = `arium:
  agents:
    - name: writer
      yaml_file: agents/writer.yaml
    - name: ns/reviewer
  workflow:
    start: writer
    edges:
      - from: writer
        to: [ns/reviewer]
    end: [ns/reviewer]
`;

const NON_ROOTFLO_YAML = `arium:
  agents:
    - name: a
      role: Analyst
      job: Analyse the input
      model:
        provider: openai
        name: gpt-4o
        base_url: https://llm.example.com/v1
        api_key: sk-test
        organization: org-1
      settings:
        temperature: 0
        max_tokens: 512
        top_p: 0.9
  workflow:
    start: a
    edges: []
    end: [a]
`;

const SUBWORKFLOW_REF_YAML = `arium:
  agents:
    - name: a
      job: Prepare the input
      model:
        provider: openai
        name: gpt-4o-mini
  ariums:
    - name: "ns/wf@3"
  workflow:
    start: a
    edges:
      - from: a
        to: [wf]
    end: [wf]
`;

const FIELD_MATCH_YAML = `arium:
  agents:
    - name: a
    - name: technical
    - name: creative
    - name: editor
  routers:
    - name: r
      type: field_match
      field: category
      routes:
        tech: technical
        technical_docs: technical
        creative: creative
      default: editor
  workflow:
    start: a
    edges:
      - from: a
        router: r
        to: [technical, creative, editor]
      - from: technical
        to: [editor]
      - from: creative
        to: [editor]
    end: [editor]
`;

const SMART_ROUTER_YAML = `arium:
  agents:
    - name: a
    - name: tech
    - name: editor
  routers:
    - name: r
      type: smart
      routing_options:
        tech: "Technical questions"
        editor: ""
      model:
        provider: openai
        name: gpt-4o-mini
        base_url: https://llm.example.com/v1
      settings:
        temperature: 0.3
        context_description: "a support workflow"
        fallback_strategy: first
        custom_setting: true
  workflow:
    start: a
    edges:
      - from: a
        router: r
        to: [tech, editor]
      - from: tech
        to: [editor]
    end: [editor]
`;

const EXTRA_KEYS_YAML = `metadata:
  name: extras
  owner: someone
arium:
  extra_arium_key: 1
  agents:
    - name: a
      role: Researcher
      job: Research the topic
      model:
        provider: rootflo
        model_id: abc-123
        custom_model_key: 1
      settings:
        temperature: 0.5
        top_p: 0.9
      max_retries: 3
      examples:
        - input: x
          output: y
      x_custom:
        deep: [1, 2]
  function_nodes:
    - name: fn
      function_name: do_it
      custom_fn_key: keep
      prefilled_params:
        a: 1
  workflow:
    start: a
    extra_workflow_key: z
    edges:
      - from: a
        to: [fn]
    end: [fn]
`;

// a -> router r -> (b, c); b and c read other nodes' output
const EDIT_YAML = `arium:
  agents:
    - name: a
      job: first
      model:
        provider: openai
        name: gpt-4o
        base_url: https://llm.example.com/v1
      custom: keep-a
    - name: b
      job: second
      model:
        provider: rootflo
        model_id: m1
      input_filter: [a]
      custom: keep-b
      settings:
        temperature: 0.2
        top_p: 0.9
    - name: c
      job: third
      model:
        provider: openai
        name: gpt-4o
      input_filter: [a, b]
  routers:
    - name: r
      type: smart
      routing_options:
        b: "to b"
        c: "to c"
      model:
        provider: openai
        name: gpt-4o
      settings:
        context_description: ctx
  workflow:
    start: a
    edges:
      - from: a
        router: r
        to: [b, c]
    end: [b, c]
`;

const ROUND_TRIP_FIXTURES: Record<string, string> = {
  'default create-workflow yaml': DEFAULT_YAML,
  "stored agent referenced as 'ns/agent'": STORED_AGENT_YAML,
  'agent with yaml_file': YAML_FILE_AGENT_YAML,
  'non-rootflo agent with extra model keys': NON_ROOTFLO_YAML,
  "subworkflow reference 'ns/wf@3'": SUBWORKFLOW_REF_YAML,
  'field_match router with routes and default': FIELD_MATCH_YAML,
  'smart router with settings.context_description': SMART_ROUTER_YAML,
  'unknown extra keys on agent, function node, arium and workflow': EXTRA_KEYS_YAML,
  'edit fixture': EDIT_YAML,
};

// ---------------------------------------------------------------------------
// Round trip
// ---------------------------------------------------------------------------

describe('yamlSync round trip', () => {
  it.each(Object.entries(ROUND_TRIP_FIXTURES))('parse then serialize keeps the document: %s', (_name, text) => {
    const { parsed, after, before } = roundTrip(text);
    expect(parsed.error).toBeUndefined();
    expect(parsed.nodes.length).toBeGreaterThan(0);
    expect(after).toEqual(before);
  });

  it('default yaml produces no serialize issues', () => {
    expect(roundTrip(DEFAULT_YAML).result.issues).toEqual([]);
  });

  it('is stable: a second parse and serialize gives the same document', () => {
    const first = roundTrip(DEFAULT_YAML);
    const second = roundTrip(first.result.yaml);
    expect(second.after).toEqual(first.after);
  });

  it("reads a stored agent as a node named 'ns/agent'", () => {
    const parsed = parseOk(STORED_AGENT_YAML);
    expect(parsed.nodes.some((n) => n.id === 'ns/agent' && n.type === NODE_TYPES.AGENT)).toBe(true);
  });

  it("reads subworkflow 'ns/wf@3' as node 'wf' that keeps its reference", () => {
    const parsed = parseOk(SUBWORKFLOW_REF_YAML);
    const node = parsed.nodes.find((n) => n.id === 'wf');
    expect(node?.type).toBe(NODE_TYPES.SUBWORKFLOW);
    expect(node?.data.ref).toBe('ns/wf@3');
  });

  it('keeps a non-rootflo model block untouched', () => {
    const { after, before } = roundTrip(NON_ROOTFLO_YAML);
    expect(after.arium.agents[0].model).toEqual(before.arium.agents[0].model);
    expect(after.arium.agents[0].model.model_id).toBeUndefined();
    expect(after.arium.agents[0].settings.temperature).toBe(0);
  });

  it('keeps smart router settings.context_description and unknown settings', () => {
    const { after } = roundTrip(SMART_ROUTER_YAML);
    const router = after.arium.routers[0];
    expect(router.settings.context_description).toBe('a support workflow');
    expect(router.settings.custom_setting).toBe(true);
    expect(router.routing_options).toEqual({ tech: 'Technical questions', editor: '' });
    expect(router.model.base_url).toBe('https://llm.example.com/v1');
  });

  it('writes field_match routes back, merging values that share a target', () => {
    const { parsed, after } = roundTrip(FIELD_MATCH_YAML);
    const router = parsed.nodes.find((n) => n.id === 'r');
    expect(router?.data.routing_options).toEqual({
      technical: 'tech | technical_docs',
      creative: 'creative',
      editor: '',
    });
    expect(after.arium.routers[0].routes).toEqual({
      tech: 'technical',
      technical_docs: 'technical',
      creative: 'creative',
    });
    expect(after.arium.routers[0].default).toBe('editor');
    expect(after.arium.routers[0].model).toBeUndefined();
  });

  it('preserves unknown keys on agent, function node, arium and workflow', () => {
    const { after } = roundTrip(EXTRA_KEYS_YAML);
    expect(after.arium.agents[0].max_retries).toBe(3);
    expect(after.arium.agents[0].examples).toEqual([{ input: 'x', output: 'y' }]);
    expect(after.arium.agents[0].x_custom).toEqual({ deep: [1, 2] });
    expect(after.arium.agents[0].model.custom_model_key).toBe(1);
    expect(after.arium.function_nodes[0].custom_fn_key).toBe('keep');
    expect(after.arium.extra_arium_key).toBe(1);
    expect(after.arium.workflow.extra_workflow_key).toBe('z');
    expect(after.metadata).toEqual({ name: 'extras', owner: 'someone' });
  });
});

describe('yamlSync documented differences', () => {
  it('drops a stale workflow.end entry that has outgoing edges', () => {
    const text = `arium:
  agents:
    - name: a
    - name: b
  workflow:
    start: a
    edges:
      - from: a
        to: [b]
    end: [a, b]
`;
    const { before, after } = roundTrip(text);
    expect(after.arium.workflow.end).toEqual(['b']);
    expect({ ...after.arium.workflow, end: undefined }).toEqual({ ...before.arium.workflow, end: undefined });
    expect(after.arium.agents).toEqual(before.arium.agents);
  });

  it('writes an edges key for a single-node workflow', () => {
    const text = `arium:
  agents:
    - name: a
  workflow:
    start: a
    end: [a]
`;
    const { after } = roundTrip(text);
    expect(Object.prototype.hasOwnProperty.call(after.arium.workflow, 'edges')).toBe(true);
    expect(after.arium.workflow.edges).toEqual([]);
    expect(after.arium.workflow.start).toBe('a');
    expect(after.arium.workflow.end).toEqual(['a']);
  });

  it('writes start, edges and end when the workflow block is missing', () => {
    const { after } = roundTrip(`arium:\n  agents:\n    - name: a\n`);
    expect(after.arium.workflow).toEqual({ start: 'a', edges: [], end: ['a'] });
  });

  it('keeps only one target of a plain fan-out edge and reports it', () => {
    const text = `arium:
  agents:
    - name: a
    - name: b
    - name: c
  workflow:
    start: a
    edges:
      - from: a
        to: [b, c]
    end: [b, c]
`;
    const parsed = parseOk(text);
    expect(parsed.edges.filter((e) => e.source === 'a' && e.target !== 'trigger-start')).toHaveLength(2);

    const result = serializeOk(parsed.nodes, parsed.edges, text);
    expect(result.issues.some((i) => /only one node/.test(i.message) && i.nodeId === 'a')).toBe(true);
    const after = load(result.yaml);
    expect(after.arium.workflow.edges).toEqual([{ from: 'a', to: ['b'] }]);
    // c is no longer reachable, so it is reported rather than left as a silent orphan
    expect(result.issues.some((i) => i.nodeId === 'c')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

describe('yamlSync errors', () => {
  it.each([
    ['invalid yaml', 'arium: [unclosed'],
    ['yaml without arium', 'metadata:\n  name: x\n'],
    ['a scalar document', 'just a string'],
    ['arium that is not a mapping', 'arium: nope'],
    ['an agent list that is not a list', 'arium:\n  agents: nope\n'],
    ['an agent without a name', 'arium:\n  agents:\n    - role: x\n'],
  ])('parse returns an error and an empty graph for %s', (_name, text) => {
    const parsed = parseYamlToGraph(text);
    expect(typeof parsed.error).toBe('string');
    expect(parsed.error).not.toBe('');
    expect(parsed.nodes).toEqual([]);
    expect(parsed.edges).toEqual([]);
  });

  it('gives an empty graph without an error for empty yaml', () => {
    expect(parseYamlToGraph('')).toEqual({ nodes: [], edges: [] });
  });

  it.each([
    ['invalid yaml', 'arium: [unclosed'],
    ['yaml without arium', 'metadata:\n  name: x\n'],
  ])('serialize refuses %s instead of overwriting it', (_name, text) => {
    const result = serializeGraphToYaml([], [], text);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Graph edits
// ---------------------------------------------------------------------------

// Rename the way the editor does: new id, data.yamlName = old name, every reference and edge follows
const renameByHand = (nodes: Node[], edges: Edge[], oldId: string, newId: string) => {
  const swap = (id: string) => (id === oldId ? newId : id);
  return {
    nodes: nodes.map((n) => {
      const data: Record<string, unknown> = { ...n.data };
      if (Array.isArray(data.input_filter)) data.input_filter = data.input_filter.map(swap);
      if (n.type === NODE_TYPES.ROUTER) {
        data.routing_options = Object.fromEntries(
          Object.entries(data.routing_options as Record<string, string>).map(([k, v]) => [swap(k), v])
        );
      }
      if (n.id !== oldId) return { ...n, data };
      return { ...n, id: newId, data: { ...data, label: newId, yamlName: oldId } };
    }),
    edges: edges.map((e) => ({ ...e, source: swap(e.source), target: swap(e.target) })),
  };
};

describe('yamlSync graph edits', () => {
  it('keeps preserved config under the new name after renaming a node', () => {
    const parsed = parseOk(EDIT_YAML);
    const { nodes, edges } = renameByHand(parsed.nodes, parsed.edges, 'b', 'b2');
    const after = load(serializeOk(nodes, edges, EDIT_YAML).yaml);

    const expected = load(EDIT_YAML);
    expected.arium.agents[1].name = 'b2';
    expected.arium.agents[2].input_filter = ['a', 'b2'];
    expected.arium.routers[0].routing_options = { b2: 'to b', c: 'to c' };
    expected.arium.workflow.edges = [{ from: 'a', router: 'r', to: ['b2', 'c'] }];
    expected.arium.workflow.end = ['b2', 'c'];

    expect(after).toEqual(expected);
    expect(after.arium.agents[1].custom).toBe('keep-b');
    expect(after.arium.agents[1].model).toEqual({ provider: 'rootflo', model_id: 'm1' });
    expect(after.arium.agents[1].settings).toEqual({ temperature: 0.2, top_p: 0.9 });
    expect(referencedNames(after)).not.toContain('b');
  });

  it('keeps preserved config of the start node when renamed through applyGraphAction', () => {
    const parsed = parseOk(EDIT_YAML);
    const renamed = applyGraphAction(
      { nodes: parsed.nodes, edges: parsed.edges },
      { type: 'renameNode', oldId: 'a', newId: 'a2' }
    );
    expect(renamed.nodes.some((n) => n.id === 'a2')).toBe(true);
    const after = load(serializeOk(renamed.nodes, renamed.edges, EDIT_YAML).yaml);

    const expected = load(EDIT_YAML);
    expected.arium.agents[0].name = 'a2';
    expected.arium.agents[1].input_filter = ['a2'];
    expected.arium.agents[2].input_filter = ['a2', 'b'];
    expected.arium.workflow.start = 'a2';
    expected.arium.workflow.edges = [{ from: 'a2', router: 'r', to: ['b', 'c'] }];

    expect(after).toEqual(expected);
    expect(after.arium.agents[0].custom).toBe('keep-a');
    expect(after.arium.agents[0].model.base_url).toBe('https://llm.example.com/v1');
    expect(referencedNames(after)).not.toContain('a');
  });

  it('leaves no dangling reference after deleting a node', () => {
    const parsed = parseOk(EDIT_YAML);
    const graph = applyGraphAction(
      { nodes: parsed.nodes, edges: parsed.edges },
      { type: 'deleteElements', nodeIds: ['b'] }
    );
    const after = load(serializeOk(graph.nodes, graph.edges, EDIT_YAML).yaml);

    expect(agentNames(after)).toEqual(['a', 'c']);
    expect(referencedNames(after)).not.toContain('b');
    expect(after.arium.routers[0].routing_options).toEqual({ c: 'to c' });
    expect(after.arium.workflow.edges).toEqual([{ from: 'a', router: 'r', to: ['c'] }]);
    expect(after.arium.workflow.end).toEqual(['c']);
    expect(after.arium.agents[1].input_filter).toEqual(['a']);
  });

  it('moves workflow.start and leaves no dangling reference after deleting the start node', () => {
    const parsed = parseOk(EDIT_YAML);
    const graph = applyGraphAction(
      { nodes: parsed.nodes, edges: parsed.edges },
      { type: 'deleteElements', nodeIds: ['a'] }
    );
    const after = load(serializeOk(graph.nodes, graph.edges, EDIT_YAML).yaml);

    expect(agentNames(after)).toEqual(['b', 'c']);
    expect(referencedNames(after)).not.toContain('a');
    expect(agentNames(after)).toContain(after.arium.workflow.start);
  });
});
