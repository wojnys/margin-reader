import { CheckCircle2, Sparkles } from "lucide-react";
import type { ReadingResponse as Reading } from "../../api/generated/models";
import { Spinner } from "../../components/ui/Spinner";

export function Processing({ reading }: { reading: Reading }) {
  const stages = ["pending", "queued", "reading", "learning"];
  const index = stages.indexOf(reading.status);
  return (
    <div className="processing">
      <div className="round-icon">
        <Sparkles size={27} />
      </div>
      <h2>A little meaning is on its way.</h2>
      <p>Your photograph is saved. You can leave this page and come back.</p>
      <div className="processing-stages">
        {[
          "Reading the photograph locally",
          "Writing simple summaries and learning material",
        ].map((s, i) => (
          <div key={s} className={index >= i + 2 ? "current" : ""}>
            {index > i + 2 ? (
              <CheckCircle2 size={17} />
            ) : index === i + 2 ? (
              <Spinner />
            ) : (
              <span className="stage-dot" />
            )}
            {s}
          </div>
        ))}
      </div>
      {index < 2 && (
        <p className="fine-print">
          Waiting for the processing worker. The saved job will start when it
          connects.
        </p>
      )}
    </div>
  );
}
