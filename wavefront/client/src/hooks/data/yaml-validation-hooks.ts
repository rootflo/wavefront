import { useMutation } from '@tanstack/react-query';
import { yamlValidationService } from '@app/api/yaml-validation-service';
import { YamlValidationResponse, YamlValidationResult } from '@app/types/yaml-validation';

export interface ValidateYamlVariables {
  yamlContent: string;
}

const unwrapResult = (response: YamlValidationResponse): YamlValidationResult => {
  const result = response.data.data?.data;
  if (!result) {
    throw new Error('Validation response was empty');
  }
  return result;
};

/**
 * Hook for validating agent YAML against the server without saving it.
 * Resolves to `{ valid, errors: [{ path, message }] }`; invalid YAML is a result,
 * not an error, so no notification is raised here.
 */
export const useValidateAgentYaml = () =>
  useMutation<YamlValidationResult, Error, ValidateYamlVariables>({
    mutationFn: async ({ yamlContent }) => unwrapResult(await yamlValidationService.validateAgentYaml(yamlContent)),
  });

/**
 * Hook for validating workflow YAML against the server without saving it.
 * Resolves to `{ valid, errors: [{ path, message }] }`; invalid YAML is a result,
 * not an error, so no notification is raised here.
 */
export const useValidateWorkflowYaml = () =>
  useMutation<YamlValidationResult, Error, ValidateYamlVariables>({
    mutationFn: async ({ yamlContent }) => unwrapResult(await yamlValidationService.validateWorkflowYaml(yamlContent)),
  });
