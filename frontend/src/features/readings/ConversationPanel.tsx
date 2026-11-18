import { MessageCircle, Sparkles } from "lucide-react";
import type { ReadingResponse } from "../../api/generated/models";
import { generateReadingConversation } from "../../api/generated/readings/readings";
import { Spinner } from "../../components/ui/Spinner";

interface Props {
  reading: ReadingResponse;
  busy: boolean;
  perform: (action: () => Promise<void>) => Promise<void>;
  update: (reading: ReadingResponse) => void;
}

export function ConversationPanel({ reading, busy, perform, update }: Props) {
  const conversation = reading.conversation;
  const generating =
    conversation &&
    ["pending", "queued", "generating"].includes(conversation.status);
  return (
    <section aria-label="Use it in conversation">
      <div className="section-intro">
        <div>
          <span className="small-label">USE IT IN CONVERSATION</span>
          <p>A few expressions from your book, ready for everyday life.</p>
        </div>
        <MessageCircle size={20} />
      </div>
      <p className="fine-print">
        Czech explanations and new English examples for work, friends, and
        everyday errands. Examples are teaching material, not quotations from
        the book.
      </p>
      {generating ? (
        <div className="conversation-state" role="status">
          <Spinner /> Preparing practical examples. You can keep reading.
        </div>
      ) : conversation?.status !== "complete" ? (
        <div className="expression-refresh">
          <div>
            <strong>
              {conversation?.status === "failed"
                ? "Let’s try these expressions again"
                : "Bring the book into your conversations"}
            </strong>
            <p>
              {conversation?.error ||
                "Choose up to three useful expressions and see how to use them. This uses AI credits."}
            </p>
          </div>
          <button
            className="button secondary small"
            disabled={
              busy || reading.status !== "complete" || reading.is_sample
            }
            onClick={() =>
              perform(async () => {
                const next = await generateReadingConversation(reading.id, {
                  revision: reading.revision,
                });
                update({ ...reading, conversation: next });
              })
            }
          >
            <Sparkles size={15} />{" "}
            {conversation?.status === "failed"
              ? "Retry examples"
              : "Create examples"}
          </button>
        </div>
      ) : null}
      {reading.is_sample && (
        <p className="muted">
          Upload your own pages to generate conversation examples.
        </p>
      )}
      <div className="expression-list">
        {conversation?.cards.map((card) => (
          <article
            className="expression-card conversation-card"
            key={card.source_index}
          >
            <div className="expression-heading">
              <div>
                <span className="expression-kind">FROM YOUR READING</span>
                <h3>{card.expression}</h3>
                <p lang="cs">{card.meaning_cs}</p>
              </div>
            </div>
            <p lang="cs">{card.explanation_cs}</p>
            <blockquote>
              “{card.source_sentence}”
              <span>{card.page_side} page · Book quotation</span>
            </blockquote>
            <div className="conversation-guidance" lang="cs">
              <p>
                <strong>Jak frázi použít: </strong>
                {card.pattern_cs}
              </p>
              <p>
                <strong>Kdy se hodí: </strong>
                {card.register_cs}
              </p>
            </div>
            <span className="small-label">NEW CONVERSATIONAL EXAMPLES</span>
            <div className="conversation-examples">
              {(
                [
                  ["work", "At work"],
                  ["social", "With friends"],
                  ["errands", "Everyday errands"],
                ] as const
              ).map(([key, label]) => (
                <div className="example" key={key}>
                  <h4>{label}</h4>
                  <p lang="en">{card[key].example_en}</p>
                  <small lang="cs">{card[key].example_cs}</small>
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
