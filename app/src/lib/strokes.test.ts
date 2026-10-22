import { describe, expect, it } from "vitest";
import type { Stroke } from "./draft";
import { hasInk, outlineToPath, strokeOutline } from "./strokes";

const pen = (points: [number, number, number][], pressure = false): Stroke => ({ tool: "pen", size: 6, points, pressure });
const clear: Stroke = { tool: "clear", size: 0, points: [], pressure: false };
const eraser: Stroke = { tool: "eraser", size: 24, points: [[10, 10, 0.5]], pressure: false };

describe("outlineToPath", () => {
  it("returns an empty path for no points", () => {
    expect(outlineToPath([])).toBe("");
  });

  it("closes a curve through the outline", () => {
    const path = outlineToPath(strokeOutline(pen([[10, 10, 0.5], [60, 40, 0.5], [120, 80, 0.5]])));
    expect(path.startsWith("M ")).toBe(true);
    expect(path.endsWith(" Z")).toBe(true);
  });

  it("draws a dot for a single tap", () => {
    expect(strokeOutline(pen([[50, 50, 0.5]])).length).toBeGreaterThan(2);
  });
});

describe("stylus pressure", () => {
  it("varies the width only when the stroke has pressure", () => {
    const points: [number, number, number][] = [[0, 0, 0.1], [40, 0, 0.1], [80, 0, 1], [120, 0, 1]];
    const height = (outline: number[][]) => Math.max(...outline.map((p) => p[1])) - Math.min(...outline.map((p) => p[1]));
    expect(height(strokeOutline(pen(points, true)))).toBeGreaterThan(0);
    const light = strokeOutline(pen(points.map(([x, y]) => [x, y, 0.1]), true));
    const heavy = strokeOutline(pen(points.map(([x, y]) => [x, y, 1]), true));
    expect(height(heavy)).toBeGreaterThan(height(light));
    const fingerLight = strokeOutline(pen(points.map(([x, y]) => [x, y, 0.1]), false));
    const fingerHeavy = strokeOutline(pen(points.map(([x, y]) => [x, y, 1]), false));
    expect(height(fingerHeavy)).toBeCloseTo(height(fingerLight), 5);
  });
});

describe("hasInk", () => {
  it("is false for nothing or only erasers", () => {
    expect(hasInk(undefined)).toBe(false);
    expect(hasInk({ strokes: [] })).toBe(false);
    expect(hasInk({ strokes: [eraser] })).toBe(false);
  });

  it("follows the last clear", () => {
    expect(hasInk({ strokes: [pen([[1, 1, 0.5]])] })).toBe(true);
    expect(hasInk({ strokes: [pen([[1, 1, 0.5]]), clear] })).toBe(false);
    expect(hasInk({ strokes: [pen([[1, 1, 0.5]]), clear, pen([[2, 2, 0.5]])] })).toBe(true);
  });

  it("counts a base image until it is cleared", () => {
    expect(hasInk({ strokes: [], base: "data:" })).toBe(true);
    expect(hasInk({ strokes: [clear], base: "data:" })).toBe(false);
  });
});
