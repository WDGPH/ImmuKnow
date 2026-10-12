interface Validator {
  (value: unknown): boolean;
  errors: null | { instancePath: string; message?: string }[];
}
declare const validators: { validatePayload: Validator; validateReport: Validator };
export default validators;
