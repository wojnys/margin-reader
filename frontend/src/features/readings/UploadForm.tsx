import { Leaf, Sparkles, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { Spinner } from "../../components/ui/Spinner";

export function UploadForm({
  busy,
  onUpload,
}: {
  busy: boolean;
  onUpload: (data: FormData) => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (file) void onUpload(new FormData(e.currentTarget));
      }}
    >
      <label className="upload-drop">
        {preview ? (
          <img src={preview} alt="Photograph selected for analysis" />
        ) : (
          <>
            <span className="round-icon">
              <Upload size={25} />
            </span>
            <strong>Choose a photograph</strong>
            <span>or drop it here</span>
          </>
        )}
        <input
          aria-label="Book photograph"
          type="file"
          name="image"
          accept="image/jpeg,image/png,image/webp"
          required
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
      </label>
      {file && (
        <p className="fine-print">
          {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB
        </p>
      )}
      <label>
        Page numbers <span className="optional">optional</span>
        <input name="page_label" maxLength={100} placeholder="e.g. 24–25" />
      </label>
      <div className="upload-hint">
        <Leaf size={16} />
        <p>
          Include both pages. Good light and a flat book help with the small
          print.
        </p>
      </div>
      <button className="button primary full-width" disabled={!file || busy}>
        {busy ? <Spinner /> : <Sparkles size={17} />} Translate & explore
      </button>
      <p className="fine-print center-text">
        Sends your photograph and reading context to DeepInfra.
      </p>
    </form>
  );
}
