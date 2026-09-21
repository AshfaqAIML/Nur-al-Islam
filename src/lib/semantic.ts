/**
 * Semantic search abstraction (Phase 5).
 *
 * The current engine is lexical (SQLite + in-JS substring scoring). This
 * module defines the provider interface a future vector/embeddings backend
 * plugs into — WITHOUT changing the database (Prisma + SQLite stays) and
 * WITHOUT touching default ranking. Ships with a dependency-free TF-IDF
 * cosine provider used opt-in via GET /api/search?semantic=1.
 */
export interface SemanticDoc {
  id: string;
  text: string;
}

export interface SemanticProvider {
  readonly name: string;
  /** Cosine-similarity scores in [0,1], aligned with `docs` order. */
  score(query: string, docs: SemanticDoc[]): Promise<number[]>;
}

export function cosine(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  if (na === 0 || nb === 0) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

function tokenize(text: string): string[] {
  return text.toLowerCase().split(/\s+/).filter((t) => t.length > 1);
}

/**
 * TF-IDF cosine provider: term-weighted overlap that degrades gracefully to
 * zeros on empty/unknown input. Interchangeable with a future embeddings
 * provider behind SemanticProvider (e.g. a sqlite-vec / remote-embedding
 * implementation — same interface, no caller changes).
 */
export class TfidfProvider implements SemanticProvider {
  readonly name = "tfidf-cosine-v1";

  async score(query: string, docs: SemanticDoc[]): Promise<number[]> {
    const qTokens = tokenize(query);
    if (qTokens.length === 0 || docs.length === 0) return docs.map(() => 0);
    const docTokens = docs.map((d) => tokenize(d.text));
    const df = new Map<string, number>();
    for (const toks of docTokens) {
      for (const t of new Set(toks)) df.set(t, (df.get(t) ?? 0) + 1);
    }
    const n = docs.length;
    const idf = (t: string) => Math.log(1 + n / (1 + (df.get(t) ?? 0)));
    const vocab = [...new Set([...qTokens, ...docTokens.flat()])];
    const vec = (toks: string[]) => {
      const tf = new Map<string, number>();
      for (const t of toks) tf.set(t, (tf.get(t) ?? 0) + 1);
      return vocab.map((t) => ((tf.get(t) ?? 0) / Math.max(1, toks.length)) * idf(t));
    };
    const qv = vec(qTokens);
    return docTokens.map((toks) => cosine(qv, vec(toks)));
  }
}

/**
 * Blend semantic similarity into lexical hits. `weight` scales the cosine
 * bonus (default 3 ≈ one title-term hit). Stable sort: lexical ties keep
 * their order; semantic only reorders across the bonus.
 */
export async function rerank<T extends { id?: string; entityId: string; entityType?: string; title: string; body?: string | null; snippet?: string; score: number }>(
  hits: T[],
  query: string,
  provider: SemanticProvider = new TfidfProvider(),
  weight = 3,
): Promise<(T & { semanticScore: number })[]> {
  if (hits.length === 0) return [];
  const sims = await provider.score(
    query,
    hits.map((h, i) => ({ id: h.id ?? `${h.entityType ?? "doc"}:${h.entityId}:${i}`, text: `${h.title} ${h.body ?? h.snippet ?? ""}` })),
  );
  return hits
    .map((h, i) => ({ ...h, semanticScore: Math.round(sims[i] * 1000) / 1000, score: h.score + weight * sims[i] }))
    .sort((a, b) => b.score - a.score);
}
