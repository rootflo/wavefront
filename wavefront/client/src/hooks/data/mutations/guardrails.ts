import floConsoleService from '@app/api';
import { UpdateGuardrailPolicyRequest } from '@app/api/guardrails-service';
import { getGuardrailPoliciesKey, getGuardrailPolicyKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

export const useSaveGuardrailPolicy = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ namespace, data }: { namespace: string; data: UpdateGuardrailPolicyRequest }) =>
      floConsoleService.guardrailsService.updatePolicy(namespace, data),
    successMessage: 'Guardrail policy saved',
    errorMessage: 'Failed to save guardrail policy',
    invalidate: ({ namespace }) =>
      appId ? [getGuardrailPolicyKey(appId, namespace), getGuardrailPoliciesKey(appId)] : [],
  });
