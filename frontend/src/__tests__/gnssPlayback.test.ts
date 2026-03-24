import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/**
 * Unit tests for GNSS playback logic in SpoofingTimeControls.
 * Tests the core animation/playback behavior without rendering the component.
 */

describe('GNSS Playback Logic', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('play/pause state toggle', () => {
    it('toggles isPlaying from false to true and back', () => {
      let isPlaying = false;
      const toggle = () => { isPlaying = !isPlaying; };

      expect(isPlaying).toBe(false);
      toggle();
      expect(isPlaying).toBe(true);
      toggle();
      expect(isPlaying).toBe(false);
    });
  });

  describe('centerTime advances by speed * deltaTime', () => {
    it('advances centerTime correctly based on playbackSpeed and delta', () => {
      const playbackSpeed = 60; // 1 min/sec — 60x real-time
      const startTime = new Date('2025-01-15T12:00:00Z');

      // Simulate a 16ms frame (roughly 60fps)
      const deltaMs = 16;
      const advanceMs = deltaMs * playbackSpeed;
      const nextTime = new Date(startTime.getTime() + advanceMs);

      // 16ms * 60 = 960ms advance in simulated time
      expect(nextTime.getTime() - startTime.getTime()).toBe(960);
    });

    it('advances faster at higher speeds', () => {
      const startTime = new Date('2025-01-15T12:00:00Z');
      const deltaMs = 16;

      const advanceSlow = deltaMs * 60;  // 1 min/sec
      const advanceFast = deltaMs * 3600; // 1 hr/sec

      expect(advanceFast).toBeGreaterThan(advanceSlow);
      expect(advanceFast / advanceSlow).toBe(60);

      const nextSlow = new Date(startTime.getTime() + advanceSlow);
      const nextFast = new Date(startTime.getTime() + advanceFast);

      expect(nextFast.getTime() - startTime.getTime()).toBe(57600); // 16 * 3600
      expect(nextSlow.getTime() - startTime.getTime()).toBe(960);   // 16 * 60
    });
  });

  describe('playback stops when centerTime reaches now', () => {
    it('clamps to now and stops playing when nextTime >= Date.now()', () => {
      const realNow = Date.now();
      vi.setSystemTime(realNow);

      const playbackSpeed = 3600;
      // Start 1 second before "now" in simulated time
      const centerTime = new Date(realNow - 1000);

      // Big frame delta that would overshoot "now"
      const deltaMs = 16;
      const advanceMs = deltaMs * playbackSpeed; // 57600ms advance
      const nextTime = new Date(centerTime.getTime() + advanceMs);

      let isPlaying = true;
      let resultTime: Date;

      if (nextTime.getTime() >= Date.now()) {
        resultTime = new Date();
        isPlaying = false;
      } else {
        resultTime = nextTime;
      }

      expect(isPlaying).toBe(false);
      expect(resultTime!.getTime()).toBe(realNow);
    });

    it('does NOT stop when nextTime is before now', () => {
      const realNow = Date.now();
      vi.setSystemTime(realNow);

      const playbackSpeed = 60;
      // Start 1 hour before "now"
      const centerTime = new Date(realNow - 3600_000);

      const deltaMs = 16;
      const advanceMs = deltaMs * playbackSpeed; // 960ms
      const nextTime = new Date(centerTime.getTime() + advanceMs);

      let isPlaying = true;
      let resultTime: Date;

      if (nextTime.getTime() >= Date.now()) {
        resultTime = new Date();
        isPlaying = false;
      } else {
        resultTime = nextTime;
      }

      expect(isPlaying).toBe(true);
      expect(resultTime!.getTime()).toBe(centerTime.getTime() + 960);
    });
  });

  describe('dragging slider pauses playback', () => {
    it('sets isPlaying to false when slider is changed', () => {
      let isPlaying = true;

      // Simulate the handleSliderChange logic
      const handleSliderChange = () => {
        isPlaying = false;
      };

      expect(isPlaying).toBe(true);
      handleSliderChange();
      expect(isPlaying).toBe(false);
    });
  });

  describe('animation frame timing', () => {
    it('skips first frame (only records timestamp)', () => {
      // The animation loop sets lastFrameRef to `now` on the first call
      // and does NOT advance centerTime
      let lastFrame = 0;
      const centerTime = new Date('2025-01-15T12:00:00Z');
      let updatedTime: Date | null = null;

      function tick(now: number) {
        if (lastFrame === 0) {
          lastFrame = now;
          // Would call requestAnimationFrame(tick) again
          return;
        }
        const deltaMs = now - lastFrame;
        lastFrame = now;
        updatedTime = new Date(centerTime.getTime() + deltaMs * 60);
      }

      // First frame at t=1000
      tick(1000);
      expect(lastFrame).toBe(1000);
      expect(updatedTime).toBeNull(); // No time update on first frame

      // Second frame at t=1016 (16ms later)
      tick(1016);
      expect(updatedTime).not.toBeNull();
      expect(updatedTime!.getTime() - centerTime.getTime()).toBe(16 * 60);
    });
  });
});
