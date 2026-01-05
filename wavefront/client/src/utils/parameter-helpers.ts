/**
 * Type-safe helper functions for accessing parameters from Record<string, unknown>
 * These functions provide safe type checking and default values for parameter access.
 */

/**
 * Safely extracts a boolean value from parameters
 */
export const getBooleanParameter = (parameters: Record<string, unknown>, key: string): boolean => {
  const value = parameters[key];
  return typeof value === 'boolean' ? value : false;
};

/**
 * Safely extracts a string value from parameters
 */
export const getStringParameter = (parameters: Record<string, unknown>, key: string): string => {
  const value = parameters[key];
  return typeof value === 'string' ? value : '';
};

/**
 * Safely extracts a number or string value from parameters
 */
export const getNumberOrStringParameter = (parameters: Record<string, unknown>, key: string): string | number => {
  const value = parameters[key];
  if (typeof value === 'number' || typeof value === 'string') return value;
  return '';
};

/**
 * Safely extracts a number value from parameters with optional default and min fallback
 */
export const getNumberParameterWithDefault = (
  parameters: Record<string, unknown>,
  key: string,
  defaultValue?: unknown,
  min?: number
): number => {
  const val = parameters[key];
  if (typeof val === 'number') return val;
  const fallback = (typeof defaultValue === 'number' ? defaultValue : undefined) ?? min ?? 0;
  return typeof fallback === 'number' ? fallback : 0;
};

/**
 * Safely extracts a boolean value from parameters with optional default
 */
export const getBooleanParameterWithDefault = (
  parameters: Record<string, unknown>,
  key: string,
  defaultValue?: unknown
): boolean => {
  const val = parameters[key];
  if (typeof val === 'boolean') return val;
  return typeof defaultValue === 'boolean' ? defaultValue : false;
};

/**
 * Safely extracts a nested parameter value with a default
 */
const getNestedParameter = <T>(
  parameters: Record<string, unknown>,
  parentKey: string,
  childKey: string,
  defaultValue: T
): T => {
  const parentValue = parameters[parentKey];
  if (typeof parentValue === 'object' && parentValue !== null && !Array.isArray(parentValue)) {
    const childValue = (parentValue as Record<string, unknown>)[childKey];
    return (typeof childValue !== 'undefined' ? childValue : defaultValue) as T;
  }
  return defaultValue;
};

/**
 * Safely extracts a nested boolean value from parameters
 */
export const getBooleanNestedParameter = (
  parameters: Record<string, unknown>,
  parentKey: string,
  childKey: string
): boolean => {
  const value = getNestedParameter(parameters, parentKey, childKey, undefined);
  return typeof value === 'boolean' ? value : false;
};

/**
 * Safely extracts a nested string value from parameters
 */
export const getStringNestedParameter = (
  parameters: Record<string, unknown>,
  parentKey: string,
  childKey: string
): string => {
  const value = getNestedParameter(parameters, parentKey, childKey, undefined);
  return typeof value === 'string' ? value : '';
};

/**
 * Safely extracts a nested number or string value from parameters
 */
export const getNumberOrStringNestedParameter = (
  parameters: Record<string, unknown>,
  parentKey: string,
  childKey: string
): string | number => {
  const value = getNestedParameter(parameters, parentKey, childKey, undefined);
  if (typeof value === 'number' || typeof value === 'string') return value;
  return '';
};
