import { useNotifyStore } from '@app/store';
import { type BaseSyntheticEvent, useCallback, useEffect, useState } from 'react';
import type { FieldErrors, UseFormReturn } from 'react-hook-form';
import {
  EMPTY_AGENT_FORM_VALUES,
  isAgentYamlField,
  patchYamlFromForm,
  yamlToForm,
  type AgentYamlFormValues,
} from './agentYamlMapper';
import { AGENT_FIELD_LABELS, type AgentFormValues } from './schemas';

export type AgentFormTab = 'visual' | 'yaml';

const isAgentFormTab = (value: string): value is AgentFormTab => value === 'visual' || value === 'yaml';

/**
 * The YAML <-> form relationship shared by the Create and Edit agent dialogs.
 *
 * - The YAML text (yamlContent) is the source of truth; the visual fields are derived from it.
 * - Only a user edit of a visual field changes the YAML, and it patches just that field's key. Opening the
 *   dialog, switching tabs and re-deriving the form never rewrite the YAML.
 * - Switching to the builder tab, and submitting from the YAML tab, re-derive every field from the YAML, so
 *   no stale value survives and validation checks what is actually submitted.
 * - A validation failure is always reported, including for a field rendered on the other tab.
 */
export const useAgentYamlForm = <T extends AgentFormValues>(typedForm: UseFormReturn<T>) => {
  // UseFormReturn is invariant in its values type; every T here extends AgentFormValues, so this view is safe.
  const form = typedForm as unknown as UseFormReturn<AgentFormValues>;
  const { notifyError } = useNotifyStore();
  const [activeTab, setActiveTab] = useState<AgentFormTab>('visual');

  useEffect(() => {
    const subscription = form.watch((values, { name, type }) => {
      // type is 'change' only for edits made through a field; reset() and setValue() never patch the YAML.
      if (type !== 'change' || !name || !isAgentYamlField(name)) return;
      const current = values.yamlContent ?? '';
      const next = patchYamlFromForm(current, values as Partial<AgentYamlFormValues>, [name]);
      if (next !== current) form.setValue('yamlContent', next, { shouldDirty: true });
    });
    return () => subscription.unsubscribe();
  }, [form]);

  /** Loads a YAML document into the form. Opens on the YAML tab when it cannot be shown in the builder. */
  const resetFromYaml = useCallback(
    (yamlText: string, extraValues?: Partial<T>) => {
      const result = yamlToForm(yamlText);
      form.reset({
        ...EMPTY_AGENT_FORM_VALUES,
        ...extraValues,
        ...(result.ok ? result.values : {}),
        yamlContent: yamlText,
      });
      setActiveTab(result.ok ? 'visual' : 'yaml');
      if (!result.ok) form.setError('yamlContent', { type: 'manual', message: result.error });
    },
    [form]
  );

  /** Re-derives every visual field from the current YAML. Returns false (and reports why) when it cannot. */
  const deriveFormFromYaml = useCallback(
    (errorPrefix: string): boolean => {
      const result = yamlToForm(form.getValues('yamlContent'));
      if (!result.ok) {
        form.setError('yamlContent', { type: 'manual', message: result.error });
        notifyError(`${errorPrefix}: ${result.error}`);
        return false;
      }
      form.reset(
        { ...form.getValues(), ...result.values },
        { keepDefaultValues: true, keepDirty: true, keepTouched: true, keepIsSubmitted: true, keepSubmitCount: true }
      );
      return true;
    },
    [form, notifyError]
  );

  const handleTabChange = useCallback(
    (value: string) => {
      if (!isAgentFormTab(value) || value === activeTab) return;
      if (value === 'visual' && !deriveFormFromYaml('Cannot switch to the builder')) return;
      setActiveTab(value);
    },
    [activeTab, deriveFormFromYaml]
  );

  const reportInvalid = useCallback(
    (errors: FieldErrors<T>) => {
      const [field] = Object.keys(errors);
      if (!field) return;
      const message = (errors as unknown as Record<string, { message?: unknown } | undefined>)[field]?.message;
      notifyError(`${AGENT_FIELD_LABELS[field] ?? field}: ${typeof message === 'string' ? message : 'Invalid value'}`);
      // Show the tab that renders the field, so its inline message is visible. The visual fields mirror the YAML
      // at this point (see handleSubmit), so switching needs no re-derive.
      setActiveTab(field === 'yamlContent' ? 'yaml' : 'visual');
    },
    [notifyError]
  );

  /** form.handleSubmit that validates the YAML being submitted and never fails silently. */
  const handleSubmit = useCallback(
    (onValid: (data: T) => void | Promise<void>) => async (event?: BaseSyntheticEvent) => {
      event?.preventDefault();
      // While the YAML tab is active the visual fields may be stale; re-derive them from the YAML first.
      if (activeTab === 'yaml' && !deriveFormFromYaml('Cannot save')) return;
      await typedForm.handleSubmit(onValid, reportInvalid)(event);
    },
    [activeTab, deriveFormFromYaml, reportInvalid, typedForm]
  );

  return { activeTab, handleTabChange, resetFromYaml, handleSubmit };
};
