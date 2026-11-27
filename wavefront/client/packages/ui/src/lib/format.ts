/** Display form of an app (or other resource) slug: 'my-app_v2' -> 'My App V2'. */
export function formatAppName(name: string | null | undefined): string {
  if (!name) return '';
  const spaced = name.replace(/[-_]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!spaced) return '';
  return spaced
    .split(' ')
    .map((word) => (word ? word.charAt(0).toUpperCase() + word.slice(1).toLowerCase() : word))
    .join(' ');
}
