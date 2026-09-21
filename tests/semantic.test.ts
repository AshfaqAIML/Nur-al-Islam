/** Phase 5 tests — semantic abstraction (interface + TF-IDF provider). */
import { describe, expect, test } from "bun:test";
import { cosine, rerank, TfidfProvider } from "../src/lib/semantic";

describe("cosine", () => {
  test("identical vectors score 1, orthogonal 0, empty 0", () => {
    expect(cosine([1, 2, 3], [1, 2, 3])).toBeCloseTo(1, 6);
    expect(cosine([1, 0], [0, 1])).toBe(0);
    expect(cosine([], [])).toBe(0);
    expect(cosine([0, 0], [1, 1])).toBe(0);
  });
});

describe("TfidfProvider", () => {
  test("name + shape + range", async () => {
    const p = new TfidfProvider();
    expect(p.name).toBe("tfidf-cosine-v1");
    const sims = await p.score("wudu face", [
      { id: "a", text: "wudu washing the face" },
      { id: "b", text: "zakat charity wealth" },
    ]);
    expect(sims.length).toBe(2);
    expect(sims[0]).toBeGreaterThan(sims[1]);
    expect(sims.every((s) => s >= 0 && s <= 1)).toBe(true);
  });

  test("empty query/docs degrade to zeros", async () => {
    const p = new TfidfProvider();
    expect(await p.score("", [{ id: "a", text: "hello world" }])).toEqual([0]);
    expect(await p.score("hello", [])).toEqual([]);
  });

  test("rare terms outweigh common ones", async () => {
    const p = new TfidfProvider();
    const sims = await p.score("tayammum", [
      { id: "a", text: "wudu water washing" },
      { id: "b", text: "tayammum dust earth" },
    ]);
    expect(sims[1]).toBeGreaterThan(sims[0]);
  });
});

describe("rerank", () => {
  test("empty in, empty out; semanticScore attached + rounded", async () => {
    expect(await rerank([], "q")).toEqual([]);
    const out = await rerank(
      [{ entityId: "a", title: "wudu face", score: 2 }],
      "wudu",
    );
    expect(out[0].semanticScore).toBeGreaterThan(0);
    expect(out[0].score).toBeGreaterThanOrEqual(2);
  });

  test("semantic bonus can promote the topically closer hit", async () => {
    const out = await rerank(
      [
        { entityId: "a", title: "zakat rules", body: "zakat charity", score: 4 },
        { entityId: "b", title: "wudu method", body: "wudu washing face water", score: 4 },
      ],
      "how to perform wudu washing",
      new TfidfProvider(),
      10,
    );
    expect(out[0].entityId).toBe("b");
  });
});
