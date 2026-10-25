import { describe, expect, it } from 'vitest';
import { matchesSearch } from './search';

describe('matchesSearch', () => {
  it('matches any value, ignoring case', () => {
    expect(matchesSearch('PROD', 'Deepgram Production', 'deepgram')).toBe(true);
    expect(matchesSearch('gram', 'Twilio', 'deepgram')).toBe(true);
    expect(matchesSearch('azure', 'Twilio', 'deepgram')).toBe(false);
  });

  it('matches everything when the query is blank', () => {
    expect(matchesSearch('', 'anything')).toBe(true);
    expect(matchesSearch('   ', 'anything')).toBe(true);
  });

  it('ignores spaces around the query', () => {
    expect(matchesSearch('  prod ', 'Production')).toBe(true);
  });

  it('skips missing values', () => {
    expect(matchesSearch('notes', null, undefined, 'release notes')).toBe(true);
    expect(matchesSearch('notes', null, undefined)).toBe(false);
  });
});
