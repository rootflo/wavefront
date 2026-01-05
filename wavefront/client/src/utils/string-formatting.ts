/**
 * Remove underscore and convert to sentence case
 * @param val - string to remove underscore and convert to sentence case
 * @returns string in sentence case
 * @example removeUnderscoreAndSentenceCase('hello_world') => 'Hello world'
 */
export const removeUnderscoreAndSentenceCase = (val: string): string => {
  if (!val) return '';
  const words = val.split('_');
  return words
    .map((word, index) => {
      if (index === 0) {
        return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
      }
      return word.toLowerCase();
    })
    .join(' ');
};
