import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Bookmark,
  CheckCircle2,
  Leaf,
} from "lucide-react";
import { useRef, useState } from "react";
import type { VocabularyResponse as Vocabulary } from "../api/generated/models";
import { reviewExpression } from "../api/generated/practice/practice";

export function PracticePage({
  vocabulary,
  refresh,
  back,
}: {
  vocabulary: Vocabulary[];
  refresh: () => Promise<void>;
  back: () => void;
}) {
  const [queue] = useState(() =>
    vocabulary.filter((v) => new Date(v.due_at) <= new Date()),
  );
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const reviewId = useRef(crypto.randomUUID());
  const card = queue[index];
  async function rate(rating: number) {
    setBusy(true);
    setError("");
    try {
      await reviewExpression(card.id, { id: reviewId.current, rating });
      setIndex((i) => i + 1);
      setRevealed(false);
      setAnswer("");
      reviewId.current = crypto.randomUUID();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">A LITTLE REPETITION GOES A LONG WAY</div>
          <h1>Make it stick.</h1>
          <p>A quiet moment with expressions you’ve already met.</p>
        </div>
        <button className="text-button" onClick={back}>
          <ArrowLeft size={16} /> My expressions
        </button>
      </div>
      {!card ? (
        <div className="practice-complete">
          <div className="round-icon">
            <CheckCircle2 size={31} />
          </div>
          <h2>
            {queue.length ? "A little more yours." : "You’re all caught up."}
          </h2>
          <p>
            {queue.length
              ? `You practised ${queue.length} ${queue.length === 1 ? "expression" : "expressions"}. They’ll return when it’s time to review.`
              : "Save some expressions, or come back when your next reviews are due."}
          </p>
          <button className="button primary" onClick={back}>
            Back to your collection <ArrowRight size={17} />
          </button>
        </div>
      ) : (
        <div className="practice-wrap">
          <div className="practice-progress">
            <span>
              EXPRESSION {index + 1} OF {queue.length}
            </span>
            <span>{Math.round((index / queue.length) * 100)}% complete</span>
          </div>
          <div className="progress-track">
            <div style={{ width: `${(index / queue.length) * 100}%` }} />
          </div>
          <div className="practice-card">
            <span className="pill">
              <Bookmark size={13} />
              {card.kind} · {card.level}
            </span>
            <p className="practice-prompt">
              How would you say this in English?
            </p>
            <h2 lang="cs">{card.meaning_cs}</h2>
            <span className="fine-print">From {card.book_title}</span>
            <label className="practice-answer">
              <span>
                Your answer <span className="optional">optional</span>
              </span>
              <input
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="Think it, say it, or write it here…"
                onKeyDown={(e) => {
                  if (e.key === "Enter") setRevealed(true);
                }}
                autoComplete="off"
              />
            </label>
            {!revealed ? (
              <button
                className="button primary"
                onClick={() => setRevealed(true)}
              >
                Check the expression <ArrowDown size={16} />
              </button>
            ) : (
              <div className="revealed-answer">
                <div className="answer-label">
                  <CheckCircle2 size={16} /> THE EXPRESSION
                </div>
                <h3>{card.expression}</h3>
                <p>{card.example_en}</p>
                <small lang="cs">{card.example_cs}</small>
                <p className="rating-caption">How well did you remember it?</p>
                <div className="rating-buttons">
                  {["Again", "Hard", "Good", "Easy"].map((label, i) => (
                    <button
                      key={label}
                      disabled={busy}
                      className={`rating rating-${i}`}
                      onClick={() => rate(i)}
                    >
                      {label}
                      <small>
                        {["10 minutes", "Sooner", "A few days", "Later"][i]}
                      </small>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {error && (
              <div className="alert" role="alert">
                {error}
              </div>
            )}
          </div>
          <p className="practice-footnote">
            <Leaf size={14} /> This is practice, not a test. Be honest with
            yourself.
          </p>
        </div>
      )}
    </>
  );
}
