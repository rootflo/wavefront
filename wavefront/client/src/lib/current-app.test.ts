import { describe, expect, it } from 'vitest';
import { getRouteAppId } from './current-app';

describe('getRouteAppId', () => {
  it('reads the app from any page inside it', () => {
    expect(getRouteAppId('/apps/abc123')).toBe('abc123');
    expect(getRouteAppId('/apps/abc123/agents')).toBe('abc123');
    expect(getRouteAppId('/apps/abc123/workflows/wf-1/editor')).toBe('abc123');
  });

  it('is undefined on /apps pages that are not an app', () => {
    expect(getRouteAppId('/apps/edit/abc123')).toBeUndefined();
    expect(getRouteAppId('/apps/users')).toBeUndefined();
    expect(getRouteAppId('/apps/create')).toBeUndefined();
  });

  it('is undefined outside /apps', () => {
    expect(getRouteAppId('/apps')).toBeUndefined();
    expect(getRouteAppId('/login')).toBeUndefined();
    expect(getRouteAppId('/')).toBeUndefined();
  });
});
