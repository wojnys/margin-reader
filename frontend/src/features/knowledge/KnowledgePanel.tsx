import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  getBookKnowledge,
  indexBookKnowledge,
  listKnowledgeEntities,
  listKnowledgeMentions,
  reviewKnowledgeMention,
} from "../../api/generated/knowledge/knowledge";

export function KnowledgePanel({
  bookId,
  openReading,
}: {
  bookId: string;
  openReading: (id: string) => void;
}) {
  const cache = useQueryClient();
  const [reviewing, setReviewing] = useState(false);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const status = useQuery({
    queryKey: ["knowledge", bookId],
    queryFn: () => getBookKnowledge(bookId),
    enabled: !!bookId,
    refetchInterval: (query) =>
      query.state.data?.jobs.some(
        (j) => !["ready", "failed"].includes(j.status),
      )
        ? 3000
        : false,
  });
  const mentions = useQuery({
    queryKey: ["knowledge-mentions", bookId],
    queryFn: () => listKnowledgeMentions(bookId),
    enabled: !!bookId && reviewing,
  });
  const entities = useQuery({
    queryKey: ["knowledge-entities", bookId],
    queryFn: () => listKnowledgeEntities(bookId),
    enabled: !!bookId && reviewing,
  });
  async function refresh() {
    await Promise.all([
      cache.invalidateQueries({ queryKey: ["knowledge", bookId] }),
      cache.invalidateQueries({ queryKey: ["knowledge-mentions", bookId] }),
    ]);
  }
  const index = useMutation({
    mutationFn: () => indexBookKnowledge(bookId),
    onSuccess: refresh,
  });
  const review = useMutation({
    mutationFn: ({ id, entityId }: { id: string; entityId: string }) =>
      reviewKnowledgeMention(bookId, id, { entity_id: entityId || null }),
    onSuccess: refresh,
  });
  const error =
    status.error ||
    index.error ||
    mentions.error ||
    entities.error ||
    review.error;
  const working = status.data?.jobs.some(
    (j) => !["ready", "failed"].includes(j.status),
  );
  return (
    <section className="knowledge-panel" aria-label="Book search preparation">
      <div className="knowledge-toolbar">
        <div>
          <strong>Book knowledge</strong>
          <p className="fine-print">
            {status.data
              ? `${status.data.passages} passages · ${status.data.entities} entities · ${status.data.unresolved_mentions} unresolved references`
              : "Checking indexed pages…"}
          </p>
        </div>
        <button
          className="button small secondary"
          disabled={index.isPending || working}
          onClick={() => index.mutate()}
        >
          Index uploaded pages / retry · uses AI credits
        </button>
        <button
          className="text-button"
          onClick={() => setReviewing(!reviewing)}
        >
          {reviewing ? "Hide references" : "Review person references"}
        </button>
      </div>
      {working && (
        <p role="status" className="fine-print">
          Preparing search and relationships. Completed reading material remains
          available.
        </p>
      )}
      {!!status.data?.jobs.length && (
        <details>
          <summary>Indexing progress and usage</summary>
          {status.data.jobs.map((job) => (
            <p className="fine-print" key={job.id}>
              Source revision {job.revision}: {job.status} ·{" "}
              {job.input_tokens + job.output_tokens} AI tokens · $
              {job.estimated_cost.toFixed(4)}
              {job.error ? ` · ${job.error}` : ""}
              {job.warning ? ` · ${job.warning}` : ""}
            </p>
          ))}
        </details>
      )}
      {reviewing && (
        <div className="knowledge-references">
          <p className="fine-print">
            Link a reference only when the original passage establishes the
            identity. Unresolved is a valid choice.
          </p>
          {mentions.data?.map((mention) => (
            <div key={mention.id} className="knowledge-reference">
              <strong>{mention.surface}</strong>
              <p>{mention.description}</p>
              <small>{mention.resolution}</small>
              {mention.source && (
                <details>
                  <summary>
                    Original passage · {mention.source.page_label} ·{" "}
                    {mention.source.side}
                  </summary>
                  <blockquote>{mention.source.text}</blockquote>
                  <button
                    className="text-button"
                    onClick={() => openReading(mention.source!.session_id)}
                  >
                    Open original reading
                  </button>
                </details>
              )}
              <label>
                Refers to
                <select
                  value={choices[mention.id] ?? mention.entity_id ?? ""}
                  onChange={(event) =>
                    setChoices({ ...choices, [mention.id]: event.target.value })
                  }
                >
                  <option value="">Unresolved</option>
                  {entities.data
                    ?.filter((entity) => entity.kind === mention.kind)
                    .map((entity) => (
                      <option key={entity.id} value={entity.id}>
                        {entity.name} ({entity.kind})
                      </option>
                    ))}
                </select>
              </label>
              <button
                className="button small secondary"
                disabled={review.isPending}
                onClick={() =>
                  review.mutate({
                    id: mention.id,
                    entityId: choices[mention.id] ?? mention.entity_id ?? "",
                  })
                }
              >
                Save reference
              </button>
            </div>
          ))}
          {mentions.data?.length === 0 && (
            <p>No inferred or unresolved references to review yet.</p>
          )}
        </div>
      )}
      {error && (
        <p className="alert" role="alert">
          {error.message}
        </p>
      )}
    </section>
  );
}
