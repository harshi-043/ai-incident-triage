import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, buildUrl, getJson, postJson } from "../api/client";

afterEach(() => vi.unstubAllGlobals());

describe("buildUrl", () => {
  it("skips empty values and repeats array values", () => {
    expect(buildUrl("/logs", { q: "", page: 2, level: ["ERROR", "WARNING"], x: undefined })).toBe("/api/logs?page=2&level=ERROR&level=WARNING");
  });
  it("has no question mark without a query", () => {
    expect(buildUrl("/health")).toBe("/api/health");
  });
});

describe("api client errors", () => {
  it("reads the backend error envelope", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: { code: "not_found", message: "Incident not found." } }), { status: 404 })));
    await expect(getJson("/incidents/x")).rejects.toMatchObject({ status: 404, code: "not_found", message: "Incident not found." });
  });
  it("adds the first validation problem to the message", async () => {
    const body = { error: { code: "validation_error", message: "Invalid input.", details: [{ field: "gap_minutes", problem: "must be at least 1" }] } };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 422 })));
    await expect(postJson("/logs/analyze", {})).rejects.toThrow("gap_minutes: must be at least 1");
  });
  it("explains an unreachable API in plain words", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const error = (await getJson("/health").catch((e) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toMatch(/Cannot reach the API/);
  });
  it("treats a bare 502 as the API being down", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("Bad Gateway", { status: 502 })));
    await expect(getJson("/health")).rejects.toMatchObject({ code: "network_error" });
  });
});
