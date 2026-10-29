import { describe, expect, it } from "vitest";
import { DASH, formatBytes, formatCell, formatDuration, formatNumber, formatPercent, plural } from "./format";

describe("format helpers", () => {
  it("shows a dash instead of inventing a number", () => {
    expect(formatNumber(null)).toBe(DASH);
    expect(formatNumber(undefined)).toBe(DASH);
    expect(formatNumber(NaN)).toBe(DASH);
    expect(formatCell("")).toBe(DASH);
  });
  it("formats numbers and percentages", () => {
    expect(formatNumber(12345)).toBe("12,345");
    expect(formatPercent(0.153, 1)).toBe("15.3%");
  });
  it("formats sizes and counts", () => {
    expect(formatBytes(2048)).toMatch(/2(\.0)? ?KB/i);
    expect(plural(1, "record")).toBe("1 record");
    expect(plural(3, "record")).toBe("3 records");
  });
  it("formats a duration between two times", () => {
    expect(formatDuration("2026-01-01T09:00:00Z", "2026-01-01T09:20:00Z")).toContain("20");
  });
});
