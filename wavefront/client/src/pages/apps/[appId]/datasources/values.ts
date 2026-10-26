// Turning the values editor's column / value lines into a row the datasource API accepts.

export interface ValuePair {
  column: string;
  value: string;
}

/**
 * What a typed value means: numbers, true/false, null and JSON objects or lists as themselves, anything else
 * as text. So `42` stores a number and `"42"` (with quotes) stores the text 42.
 */
export const parseTypedValue = (text: string): unknown => {
  const trimmed = text.trim();
  if (trimmed === '') return '';
  if (/^(-?\d+(\.\d+)?|true|false|null)$/.test(trimmed) || /^[[{"]/.test(trimmed)) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return text;
    }
  }
  return text;
};

/** The filled-in pairs as one row object; a pair with no column name is ignored. */
export const pairsToRow = (pairs: ValuePair[]): Record<string, unknown> =>
  Object.fromEntries(
    pairs.filter((pair) => pair.column.trim()).map((pair) => [pair.column.trim(), parseTypedValue(pair.value)])
  );
