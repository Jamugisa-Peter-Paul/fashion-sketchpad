import { describe, expect, it } from "vitest";
import { addDetail, cleanDetail, countDetails, emptyDetails, fingerprint, MAX_DETAILS, removeDetail } from "./details";

describe("details", () => {
  it("cleans typed details like the gateway does", () => {
    expect(cleanDetail("  Two {flap}  Pockets. ")).toBe("two flap pockets");
    expect(cleanDetail("x".repeat(200))).toHaveLength(60);
    expect(cleanDetail(" ... ")).toBe("");
  });

  it("adds without duplicates, blanks or going over the limit", () => {
    let details = addDetail(emptyDetails(), "front", "Patch pocket");
    details = addDetail(details, "front", "patch pocket");
    details = addDetail(details, "front", "   ");
    expect(details.front).toEqual(["patch pocket"]);
    for (let i = 0; i < 20; i++) details = addDetail(details, "back", `detail ${i}`);
    expect(details.back).toHaveLength(MAX_DETAILS);
    expect(countDetails(details)).toBe(1 + MAX_DETAILS);
  });

  it("removes from one group only", () => {
    const details = { ...emptyDetails(), garment: ["hood"], front: ["hood", "zip"] };
    expect(removeDetail(details, "front", "hood")).toEqual({ ...details, front: ["zip"] });
  });

  it("fingerprints are stable and change with the sketch", () => {
    expect(fingerprint("abc")).toBe(fingerprint("abc"));
    expect(fingerprint("abc")).not.toBe(fingerprint("abd"));
    expect(countDetails(null)).toBe(0);
  });
});
