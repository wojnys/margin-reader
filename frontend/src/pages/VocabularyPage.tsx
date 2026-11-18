import {
  BookOpen,
  Bookmark,
  ChevronDown,
  GraduationCap,
  Search,
} from "lucide-react";
import { useState } from "react";
import type { VocabularyResponse as Vocabulary } from "../api/generated/models";

export function VocabularyPage({
  vocabulary,
  practice,
}: {
  vocabulary: Vocabulary[];
  practice: () => void;
}) {
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState("All levels");
  const filtered = vocabulary.filter(
    (v) =>
      (level === "All levels" || v.level === level) &&
      `${v.expression} ${v.meaning_cs} ${v.book_title}`
        .toLocaleLowerCase()
        .includes(search.toLocaleLowerCase()),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ENGLISH YOU’VE MET IN THE WILD</div>
          <h1>Words worth keeping.</h1>
          <p>
            Your own collection of expressions, with the stories they came from.
          </p>
        </div>
        <button
          className="button primary"
          disabled={!vocabulary.length}
          onClick={practice}
        >
          <GraduationCap size={18} /> A little practice
        </button>
      </div>
      <div className="library-toolbar">
        <label className="search-input">
          <Search size={18} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Find an expression, meaning, or book…"
            aria-label="Search expressions"
          />
        </label>
        <select
          aria-label="Filter by level"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
        >
          {["All levels", "B1", "B2", "C1"].map((l) => (
            <option key={l}>{l}</option>
          ))}
        </select>
      </div>
      <div className="collection-count">
        {filtered.length} {filtered.length === 1 ? "expression" : "expressions"}{" "}
        in your collection
      </div>
      {!filtered.length ? (
        <div className="empty-reading">
          <div className="round-icon">
            <Bookmark size={27} />
          </div>
          <h2>
            {vocabulary.length
              ? "Nothing here just yet."
              : "Good expressions deserve a second look."}
          </h2>
          <p>
            {vocabulary.length
              ? "Try a different search or level."
              : "Save a few expressions from a reading. You’ll find them here, ready to practise."}
          </p>
        </div>
      ) : (
        <div className="library-grid">
          {filtered.map((v) => (
            <article className="expression-card library-card" key={v.id}>
              <span className="expression-kind">
                {v.kind} · {v.level}
              </span>
              <h3>{v.expression}</h3>
              <p lang="cs">{v.meaning_cs}</p>
              <blockquote>“{v.source_sentence}”</blockquote>
              <details>
                <summary>
                  Explore this expression <ChevronDown size={15} />
                </summary>
                <p lang="cs">{v.explanation_cs}</p>
                <div className="example">
                  <p>{v.example_en}</p>
                  <small lang="cs">{v.example_cs}</small>
                </div>
              </details>
              <div className="library-card-footer">
                <span>
                  <BookOpen size={13} />
                  {v.book_title}
                </span>
                <span>
                  {new Date(v.due_at) <= new Date()
                    ? "Ready to practise"
                    : `Review ${new Date(v.due_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`}
                </span>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
