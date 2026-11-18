import { Leaf, Sparkles } from "lucide-react";

export function BookIllustration() {
  return (
    <div className="book-illustration" aria-hidden="true">
      <div className="illustration-orbit orbit-one" />
      <div className="illustration-orbit orbit-two" />
      <span className="floating-leaf">
        <Leaf size={27} />
      </span>
      <div className="drawn-book">
        <div className="book-half left-half">
          <span className="drawing-kicker">A NEW CHAPTER</span>
          <div className="drawing-title">
            The world
            <br />
            between
            <br />
            the lines.
          </div>
          <div className="ink-lines" />
        </div>
        <div className="book-half right-half">
          <div className="ink-lines" />
          <span className="highlight-line" />
          <div className="ink-lines short-lines" />
          <span className="book-page">24</span>
        </div>
        <div className="ribbon" />
      </div>
      <span className="translation-note">
        <Sparkles size={15} /> a little clearer
      </span>
    </div>
  );
}
