import type { ReadingResponse as Reading } from "../api/generated/models";
import {
  ArrowRight,
  BookOpen,
  Bookmark,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileText,
  Leaf,
  MessageCircle,
  Plus,
  Search,
  Smartphone,
  Sparkles,
  Upload,
} from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import type { BookResponse } from "../api/generated/models";
import {
  getGetReadingImageUrl,
  refreshReadingLearning,
  retryReading,
} from "../api/generated/readings/readings";
import type { Modal, Tab } from "../app/types";
import { Spinner } from "../components/ui/Spinner";
import { BookIllustration } from "../features/readings/BookIllustration";
import { Processing } from "../features/readings/Processing";
import { ConversationPanel } from "../features/readings/ConversationPanel";
const activeStatuses = ["pending", "queued", "reading", "learning"];
interface Props {
  book?: BookResponse;
  reading?: Reading;
  readings: Reading[];
  tab: Tab;
  setTab: (tab: Tab) => void;
  setModal: (modal: Modal) => void;
  busy: boolean;
  sample: () => Promise<void>;
  openPhone: () => Promise<void>;
  readingId: string;
  setReadingId: (id: string) => void;
  perform: (action: () => Promise<void>) => Promise<void>;
  setReadings: Dispatch<SetStateAction<Reading[]>>;
  saveExpression: (index: number) => Promise<void>;
}
export function ReadingPage({
  book,
  reading,
  readings,
  tab,
  setTab,
  setModal,
  busy,
  sample,
  openPhone,
  readingId,
  setReadingId,
  perform,
  setReadings,
  saveExpression,
}: Props) {
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">READ AT YOUR OWN PACE</div>
          <h1>{book ? book.title : "Your reading room"}</h1>
          <p>
            {book
              ? `${book.author || "Your book"} · ${book.level} learning level`
              : "For the stories you love. And the English you’re making your own."}
          </p>
        </div>
        {book && (
          <button className="button primary" onClick={() => setModal("upload")}>
            <Plus size={17} /> Add pages
          </button>
        )}
      </div>
      {!book ? (
        <>
          <section className="welcome-card">
            <div className="welcome-copy">
              <span className="pill">
                <Sparkles size={13} /> A NEW WAY TO READ
              </span>
              <h2>
                Read the story.
                <br />
                <em>Keep the meaning.</em>
              </h2>
              <p>
                A little help with the difficult parts.
                <br />A few new expressions to carry with you.
              </p>
              <button
                className="button primary"
                onClick={() => setModal("book")}
              >
                Start with a book <ArrowRight size={17} />
              </button>
              <button
                className="text-button sample-button"
                disabled={busy}
                onClick={sample}
              >
                Or explore a sample reading <ChevronRight size={14} />
              </button>
            </div>
            <BookIllustration />
          </section>
          <div className="how-heading">
            <span>A SIMPLE READING RITUAL</span>
            <span>From the page to your everyday English</span>
          </div>
          <div className="ritual-grid">
            {[
              {
                icon: Upload,
                n: "01",
                title: "Bring a page",
                text: "Photograph an open book on your phone, or upload from your computer.",
              },
              {
                icon: BookOpen,
                n: "02",
                title: "Find the meaning",
                text: "Read clear English summaries, then check your understanding with helpful answers.",
              },
              {
                icon: Bookmark,
                n: "03",
                title: "Make it yours",
                text: "Save useful expressions. Come back for a little practice when they’re due.",
              },
            ].map(({ icon: Icon, n, title, text }) => (
              <article className="ritual" key={n}>
                <div className="ritual-top">
                  <Icon size={21} />
                  <span>{n}</span>
                </div>
                <h3>{title}</h3>
                <p>{text}</p>
              </article>
            ))}
          </div>
          <div className="quiet-note">
            <Leaf size={15} /> You don’t need to understand every word to enjoy
            a good story.
          </div>
        </>
      ) : (
        <>
          <div className="reading-toolbar">
            <div>
              <span className="small-label">READING SESSIONS</span>
              <span className="session-total">{readings.length}</span>
            </div>
            <button className="text-button" onClick={openPhone}>
              <Smartphone size={16} /> Connect your phone{" "}
              <ArrowRight size={14} />
            </button>
          </div>
          {!readings.length ? (
            <section className="empty-reading">
              <div className="round-icon">
                <BookOpen size={28} />
              </div>
              <h2>A new chapter starts here.</h2>
              <p>
                Open your book, photograph both pages, and let’s make sense of
                them together.
              </p>
              <div className="button-row">
                <button
                  className="button primary"
                  onClick={() => setModal("upload")}
                >
                  <Upload size={17} /> Upload a photograph
                </button>
                <button className="button secondary" onClick={openPhone}>
                  <Smartphone size={17} /> Use your phone
                </button>
              </div>
              <span className="fine-print">
                JPEG, PNG, or WebP · Up to 20 MB · Both pages in one photograph
              </span>
            </section>
          ) : (
            <div className="reading-layout">
              <aside className="session-list">
                {readings.map((r, i) => (
                  <button
                    key={r.id}
                    className={`session-item ${readingId === r.id ? "selected" : ""}`}
                    onClick={() => {
                      setReadingId(r.id);
                      setTab("summary");
                    }}
                  >
                    <span className="session-symbol">
                      <FileText size={18} />
                    </span>
                    <span>
                      <strong>
                        {r.page_label
                          ? `Pages ${r.page_label}`
                          : `Reading ${readings.length - i}`}
                      </strong>
                      {r.learning?.topic_title && (
                        <small className="session-topic">
                          {r.learning.topic_title}
                        </small>
                      )}
                      <small>
                        {new Date(r.created_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                        })}{" "}
                        ·{" "}
                        {r.is_sample
                          ? "Sample"
                          : r.status === "complete"
                            ? "Ready to read"
                            : r.status}
                      </small>
                    </span>
                    {activeStatuses.includes(r.status) ? (
                      <Spinner />
                    ) : r.status === "complete" ? (
                      <Check size={14} />
                    ) : (
                      <CircleHelp size={16} />
                    )}
                  </button>
                ))}
                <button
                  className="new-session"
                  onClick={() => setModal("upload")}
                >
                  <Plus size={16} /> A few more pages
                </button>
              </aside>
              {reading && (
                <section className="reading-panel">
                  <div className="reading-panel-heading">
                    <div>
                      <span className="eyebrow">
                        {reading.is_sample
                          ? "SAMPLE READING · NO AI CREDITS USED"
                          : "YOUR LATEST CHAPTER"}
                      </span>
                      <h2>
                        {reading.page_label
                          ? `Pages ${reading.page_label}`
                          : "Between the lines"}
                      </h2>
                      {reading.learning?.topic_title && (
                        <p className="reading-topic">
                          {reading.learning.topic_title}
                        </p>
                      )}
                    </div>
                    <span
                      className={`status-pill ${reading.status === "complete" ? "ready" : ""}`}
                    >
                      {reading.status === "complete" ? (
                        <CheckCircle2 size={13} />
                      ) : (
                        <Clock3 size={13} />
                      )}{" "}
                      {reading.status === "complete"
                        ? "Ready to explore"
                        : reading.status}
                    </span>
                  </div>
                  {activeStatuses.includes(reading.status) ? (
                    <Processing reading={reading} />
                  ) : (
                    <>
                      {reading.error && (
                        <div className="alert">
                          <p>{reading.error}</p>
                          <div className="button-row">
                            <button
                              className="button small secondary"
                              disabled={busy}
                              onClick={() =>
                                perform(async () => {
                                  const next = await retryReading(reading.id);
                                  setReadings((rs) =>
                                    rs.map((r) =>
                                      r.id === next.id ? next : r,
                                    ),
                                  );
                                })
                              }
                            >
                              Retry processing
                            </button>
                            <button
                              className="text-button"
                              onClick={() => setModal("edit")}
                            >
                              Enter or correct the text
                            </button>
                          </div>
                        </div>
                      )}
                      <div
                        className="reading-tabs"
                        role="tablist"
                        aria-label="Reading details"
                      >
                        {(
                          [
                            {
                              id: "summary",
                              label: "Page summaries",
                              icon: FileText,
                            },
                            {
                              id: "expressions",
                              label: "Expressions",
                              icon: Bookmark,
                            },
                            {
                              id: "conversation",
                              label: "Conversation",
                              icon: MessageCircle,
                            },
                            {
                              id: "questions",
                              label: "Check understanding",
                              icon: CircleHelp,
                            },
                            {
                              id: "source",
                              label: "Original",
                              icon: Search,
                            },
                          ] as const
                        ).map(({ id, label, icon: Icon }) => (
                          <button
                            key={id}
                            role="tab"
                            aria-selected={tab === id}
                            className={tab === id ? "active" : ""}
                            onClick={() => setTab(id)}
                          >
                            <Icon size={15} />
                            {label}
                            {id === "expressions" && reading.learning && (
                              <span>{reading.learning.expressions.length}</span>
                            )}
                          </button>
                        ))}
                      </div>
                      <div className="tab-content" role="tabpanel">
                        {tab === "conversation" && (
                          <ConversationPanel
                            reading={reading}
                            busy={busy}
                            perform={perform}
                            update={(next) =>
                              setReadings((items) =>
                                items.map((item) =>
                                  item.id === next.id ? next : item,
                                ),
                              )
                            }
                          />
                        )}
                        {tab === "summary" && (
                          <>
                            <div className="section-intro">
                              <span className="small-label">
                                THE STORY, IN CLEAR ENGLISH
                              </span>
                              <span className="subtle-tag">B1 ENGLISH</span>
                            </div>
                            <div className="translated-pages">
                              {(["left", "right"] as const).map((side) => (
                                <article className="translated-page" key={side}>
                                  <div className="page-side">
                                    <span>
                                      {side === "left"
                                        ? "LEFT PAGE"
                                        : "RIGHT PAGE"}
                                    </span>
                                    <span>{side === "left" ? "01" : "02"}</span>
                                  </div>
                                  <div className="prose">
                                    {reading.learning?.[`${side}_summary_en`] ||
                                      "The summary will appear after processing."}
                                  </div>
                                </article>
                              ))}
                            </div>
                            <p className="fine-print">
                              Each summary is based on its photographed page and
                              your previous reading context.
                            </p>
                          </>
                        )}
                        {tab === "expressions" && (
                          <>
                            <div className="section-intro">
                              <div>
                                <span className="small-label">
                                  EXPRESSIONS WORTH KEEPING
                                </span>
                                <p>Useful in this story. Useful beyond it.</p>
                              </div>
                              <span className="subtle-tag">
                                CEFR levels are approximate
                              </span>
                            </div>
                            {!reading.is_sample && (
                              <div className="expression-refresh">
                                <div>
                                  <strong>Explore more of these pages</strong>
                                  <p>
                                    Generate 10–22 expressions using the saved
                                    text. Uses AI credits.
                                  </p>
                                </div>
                                <button
                                  className="button secondary small"
                                  disabled={
                                    busy || reading.status !== "complete"
                                  }
                                  onClick={() =>
                                    perform(async () => {
                                      const next = await refreshReadingLearning(
                                        reading.id,
                                        { revision: reading.revision },
                                      );
                                      setReadings((rs) =>
                                        rs.map((r) =>
                                          r.id === next.id ? next : r,
                                        ),
                                      );
                                    })
                                  }
                                >
                                  <Sparkles size={15} /> Get 10–22 expressions
                                </button>
                              </div>
                            )}
                            <div className="expression-list">
                              {reading.learning?.expressions.map((e, index) => (
                                <article
                                  className="expression-card"
                                  key={index}
                                >
                                  <div className="expression-heading">
                                    <div>
                                      <span className="expression-kind">
                                        {e.kind} <span>·</span> {e.level}
                                      </span>
                                      <h3>{e.expression}</h3>
                                      <p lang="cs">{e.meaning_cs}</p>
                                    </div>
                                    <button
                                      className={`save-button ${reading.saved_expressions.includes(e.expression) ? "saved" : ""}`}
                                      disabled={
                                        busy ||
                                        reading.saved_expressions.includes(
                                          e.expression,
                                        )
                                      }
                                      onClick={() => saveExpression(index)}
                                    >
                                      {reading.saved_expressions.includes(
                                        e.expression,
                                      ) ? (
                                        <Check size={16} />
                                      ) : (
                                        <Plus size={16} />
                                      )}{" "}
                                      {reading.saved_expressions.includes(
                                        e.expression,
                                      )
                                        ? "Saved"
                                        : "Save"}
                                    </button>
                                  </div>
                                  <blockquote>
                                    “{e.source_sentence}”
                                    <span>{e.page_side} page</span>
                                  </blockquote>
                                  <details>
                                    <summary>
                                      Meaning & another example{" "}
                                      <ChevronDown size={14} />
                                    </summary>
                                    <p lang="cs">{e.explanation_cs}</p>
                                    <div className="example">
                                      <p>{e.example_en}</p>
                                      <small lang="cs">{e.example_cs}</small>
                                    </div>
                                  </details>
                                </article>
                              ))}
                            </div>
                          </>
                        )}
                        {tab === "questions" && (
                          <>
                            <div className="section-intro">
                              <div>
                                <span className="small-label">
                                  PAUSE, THINK, THEN CHECK
                                </span>
                                <p>
                                  Every question has an answer just below it.
                                </p>
                              </div>
                            </div>
                            {reading.learning?.questions.map((q, i) => (
                              <article className="question-card" key={i}>
                                <div className="question-number">0{i + 1}</div>
                                <h3>{q.question_en}</h3>
                                <details className="answer-box">
                                  <summary>
                                    Check the answer <ChevronDown size={16} />
                                  </summary>
                                  <p lang="cs">{q.answer_cs}</p>
                                  <blockquote>“{q.evidence_en}”</blockquote>
                                </details>
                              </article>
                            ))}
                          </>
                        )}
                        {tab === "source" && (
                          <>
                            <div className="section-intro">
                              <span className="small-label">
                                THE WORDS ON THE PAGE
                              </span>
                              <button
                                className="text-button"
                                onClick={() => setModal("edit")}
                              >
                                Correct transcription <ArrowRight size={14} />
                              </button>
                            </div>
                            {!reading.is_sample && (
                              <a
                                className="source-photo"
                                href={getGetReadingImageUrl(reading.id)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <img
                                  alt="Your photographed double page"
                                  src={getGetReadingImageUrl(reading.id)}
                                />
                                <span>Open original photograph ↗</span>
                              </a>
                            )}
                            {reading.extraction?.warnings?.map((w, i) => (
                              <div className="alert" key={i}>
                                {w}
                              </div>
                            ))}
                            <div className="translated-pages">
                              {(["left", "right"] as const).map((side) => (
                                <article key={side} className="translated-page">
                                  <div className="page-side">
                                    {side.toUpperCase()} PAGE
                                  </div>
                                  <div className="prose">
                                    {reading.extraction?.[side]
                                      .split("\n\n")
                                      .map((p, i) => (
                                        <p key={i}>{p}</p>
                                      ))}
                                  </div>
                                </article>
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    </>
                  )}
                  <div className="reading-footer">
                    <span>
                      {reading.is_sample
                        ? "Original sample written for Margin"
                        : "Your photo · Your reading context"}
                    </span>
                    <span>
                      {reading.is_sample
                        ? "No API calls"
                        : `Estimated AI cost $${reading.usage.estimated_cost.toFixed(4)} USD`}
                    </span>
                  </div>
                </section>
              )}
            </div>
          )}
        </>
      )}
    </>
  );
}
