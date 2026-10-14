import { isUnityAvailable, UnityBridge } from '..';

describe('UnityBridge', () => {
  it('is unavailable outside an Android build with Unity', () => {
    expect(isUnityAvailable).toBe(false);
    expect(UnityBridge.isRunning()).toBe(false);
    expect(() => UnityBridge.send({ type: 'restart' })).not.toThrow();
  });

  it('parses messages from the game', () => {
    expect(UnityBridge.parse('{"type":"ready"}')).toEqual({ type: 'ready' });
    expect(UnityBridge.parse('{"type":"progress","stage":1,"stageCount":5,"found":2,"required":3,"wildcards":3}')).toMatchObject({
      type: 'progress',
      found: 2,
    });
    expect(UnityBridge.parse('not json')).toBeNull();
    expect(UnityBridge.parse('{"no":"type"}')).toBeNull();
  });
});
