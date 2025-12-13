/**
 * Validation messages
 * @example validationMessage.isRequired('name') => 'Name is required'
 */
export const validationMessage = {
  onlyNumbers: 'Only numbers are allowed',
  isRequired: (fieldName: string) => `${fieldName} is required`,
  isInvalid: (fieldName: string) => `${fieldName} is invalid`,
  minValue: (fieldName: string, value: number) => `${fieldName} must be greater than or equal to ${value}`,
  maxValue: (filedName: string, value: number) => `${filedName} must be less than or equal to ${value}`,
  minLength: (fieldName: string, value: number) => `${fieldName} must be at least ${value} character long`,
  maxLength: (filedName: string, value: number) => `${filedName} must be at most ${value} character long`,
};
