import { IApiResponse } from '@app/lib/axios';

/** One problem found in a YAML document, located by its path (empty for the whole document). */
export interface YamlValidationError {
  path: string;
  message: string;
}

export interface YamlValidationResult {
  valid: boolean;
  errors: YamlValidationError[];
}

export interface YamlValidationData {
  message: string;
  data: YamlValidationResult;
}

export type YamlValidationResponse = IApiResponse<YamlValidationData>;
