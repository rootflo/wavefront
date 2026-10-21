import { describe, expect, it } from 'vitest';
import yaml from 'js-yaml';
import { patchYamlFromForm, yamlToForm, type AgentYamlField, type AgentYamlFormValues } from './agentYamlMapper';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Doc = any;

const load = (text: string): Doc => yaml.load(text);

const formOf = (text: string): AgentYamlFormValues => {
  const result = yamlToForm(text);
  if (!result.ok) throw new Error(result.error);
  return result.values;
};

const allFields = (values: AgentYamlFormValues) => Object.keys(values) as AgentYamlField[];

// Comments and quoting here must survive an untouched patch
const ROOTFLO_YAML = `# agent owned by the team
metadata:
  name: writer-agent
  description: "Writes things"
  tags: [alpha, beta]
agent:
  name: writer
  role: Writer
  job: "Write clearly."   # keep it short
  model:
    provider: rootflo
    model_id: model-1
  settings:
    temperature: 0.7
    max_tokens: 1000
    top_p: 0
  max_retries: 3
  parser:
    name: out
`;

const OPENAI_YAML = `agent:
  name: writer
  job: Write
  model:
    provider: openai
    name: gpt-4o
    base_url: https://llm.example.com/v1
    api_key: sk-test
    custom_key: 1
  settings:
    temperature: 0.2
`;

describe('yamlToForm', () => {
  it('reads every field from the YAML', () => {
    expect(formOf(ROOTFLO_YAML)).toEqual({
      agentName: 'writer',
      role: 'Writer',
      job: 'Write clearly.',
      description: 'Writes things',
      tags: 'alpha, beta',
      actAs: '',
      modelId: 'model-1',
      temperature: 0.7,
      maxTokens: 1000,
      reasoningPattern: '',
      topP: 0,
      topK: null,
      frequencyPenalty: null,
      presencePenalty: null,
      seed: null,
    });
  });

  it('reads 0 as 0, not as empty', () => {
    const values = formOf('agent:\n  name: a\n  settings:\n    temperature: 0\n    seed: 0\n');
    expect(values.temperature).toBe(0);
    expect(values.seed).toBe(0);
  });

  it('returns an error for invalid YAML and for YAML without an agent section', () => {
    expect(yamlToForm('agent: [unclosed').ok).toBe(false);
    expect(yamlToForm('metadata:\n  name: x\n').ok).toBe(false);
  });
});

describe('patchYamlFromForm', () => {
  it('returns the original text unchanged when no fields are dirty', () => {
    expect(patchYamlFromForm(ROOTFLO_YAML, formOf(ROOTFLO_YAML), [])).toBe(ROOTFLO_YAML);
  });

  it('returns the original text unchanged when every field is dirty but holds the YAML value', () => {
    const values = formOf(ROOTFLO_YAML);
    expect(patchYamlFromForm(ROOTFLO_YAML, values, allFields(values))).toBe(ROOTFLO_YAML);
  });

  it('returns the original text unchanged for invalid YAML', () => {
    const broken = 'agent: [unclosed';
    expect(patchYamlFromForm(broken, { role: 'x' }, ['role'])).toBe(broken);
  });

  it('editing one field changes only that key', () => {
    const values = { ...formOf(ROOTFLO_YAML), role: 'Editor' };
    const patched = patchYamlFromForm(ROOTFLO_YAML, values, ['role']);

    const expected = load(ROOTFLO_YAML);
    expected.agent.role = 'Editor';
    expect(load(patched)).toEqual(expected);
  });

  it('editing a settings field changes only that settings key', () => {
    const values = { ...formOf(ROOTFLO_YAML), temperature: 0.1 };
    const patched = patchYamlFromForm(ROOTFLO_YAML, values, ['temperature']);

    const expected = load(ROOTFLO_YAML);
    expected.agent.settings.temperature = 0.1;
    expect(load(patched)).toEqual(expected);
  });

  it('a field that is not marked dirty is not written even if its form value differs', () => {
    const values = { ...formOf(ROOTFLO_YAML), role: 'Editor', job: 'Other' };
    const patched = patchYamlFromForm(ROOTFLO_YAML, values, ['role']);
    expect(load(patched).agent.job).toBe('Write clearly.');
    expect(load(patched).agent.role).toBe('Editor');
  });

  it('clearing a numeric setting deletes the key and keeps the others', () => {
    const values = { ...formOf(ROOTFLO_YAML), temperature: null };
    const settings = load(patchYamlFromForm(ROOTFLO_YAML, values, ['temperature'])).agent.settings;
    expect('temperature' in settings).toBe(false);
    expect(settings).toEqual({ max_tokens: 1000, top_p: 0 });
  });

  it('removes the settings block once its last key is cleared', () => {
    const text = 'agent:\n  name: a\n  settings:\n    temperature: 0.5\n';
    const values = { ...formOf(text), temperature: null };
    const agent = load(patchYamlFromForm(text, values, ['temperature'])).agent;
    expect('settings' in agent).toBe(false);
  });

  it('preserves 0 when writing a numeric setting', () => {
    const text = 'agent:\n  name: a\n  job: j\n';
    const values = { ...formOf(text), temperature: 0, topK: 0, seed: 0 };
    const settings = load(patchYamlFromForm(text, values, ['temperature', 'topK', 'seed'])).agent.settings;
    expect(settings).toEqual({ temperature: 0, top_k: 0, seed: 0 });
  });

  it('keeps an existing 0 when its field is dirty with the same value', () => {
    const values = formOf(ROOTFLO_YAML);
    expect(values.topP).toBe(0);
    const patched = patchYamlFromForm(ROOTFLO_YAML, values, ['topP']);
    expect(load(patched).agent.settings.top_p).toBe(0);
    expect(patched).toBe(ROOTFLO_YAML);
  });

  it('never rewrites a non-rootflo model block', () => {
    const original = load(OPENAI_YAML).agent.model;
    const values = { ...formOf(OPENAI_YAML), modelId: 'rootflo-model-9' };

    const patched = patchYamlFromForm(OPENAI_YAML, values, ['modelId']);
    expect(patched).toBe(OPENAI_YAML);
    expect(load(patched).agent.model).toEqual(original);

    // also when it is dirty together with other fields
    const withOthers = patchYamlFromForm(OPENAI_YAML, { ...values, role: 'Editor', temperature: 0.9 }, [
      'modelId',
      'role',
      'temperature',
    ]);
    const doc = load(withOthers);
    expect(doc.agent.model).toEqual(original);
    expect(doc.agent.role).toBe('Editor');
    expect(doc.agent.settings.temperature).toBe(0.9);
  });

  it('does not rewrite a non-rootflo model block when every field is dirty and unchanged', () => {
    const values = formOf(OPENAI_YAML);
    expect(values.modelId).toBe('');
    expect(patchYamlFromForm(OPENAI_YAML, values, allFields(values))).toBe(OPENAI_YAML);
  });

  it('points a rootflo model at a new model id and keeps its other keys', () => {
    const values = { ...formOf(ROOTFLO_YAML), modelId: 'model-2' };
    const doc = load(patchYamlFromForm(ROOTFLO_YAML, values, ['modelId']));
    expect(doc.agent.model).toEqual({ provider: 'rootflo', model_id: 'model-2' });
    expect(doc.agent.max_retries).toBe(3);
    expect(doc.agent.parser).toEqual({ name: 'out' });
  });
});
