import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  CheckCircle2,
  ImagePlus,
  Smartphone,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  useGetCapture,
  uploadCaptureBatch,
} from "../api/generated/capture/capture";
import { Brand } from "../components/layout/Brand";
import { Spinner } from "../components/ui/Spinner";

interface Photo {
  id: string;
  file: File;
  preview: string;
  customLabel?: string;
}

const acceptedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);

export function CapturePage({ token }: { token: string }) {
  const infoQuery = useGetCapture(token, { query: { retry: false } });
  const info = infoQuery.data;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [startingPage, setStartingPage] = useState(12);
  const previews = useRef(new Set<string>());
  const photoSequence = useRef(0);
  useEffect(
    () => () => {
      previews.current.forEach((url) => URL.revokeObjectURL(url));
    },
    [],
  );
  function addPhotos(files: FileList | null) {
    if (!files) return;
    const selected = Array.from(files);
    if (photos.length + selected.length > 10) {
      setError("Choose up to 10 photographs per batch.");
      return;
    }
    if (
      selected.some(
        (file) => !acceptedTypes.has(file.type) || file.size > 20 * 1024 * 1024,
      )
    ) {
      setError(
        "Use JPEG, PNG, or WebP photographs under 20 MB each. Convert HEIC first.",
      );
      return;
    }
    if (
      [...photos.map((photo) => photo.file), ...selected].reduce(
        (total, file) => total + file.size,
        0,
      ) >
      80 * 1024 * 1024
    ) {
      setError("Keep the batch under 80 MB in total.");
      return;
    }
    setError("");
    const added = selected.map((file) => {
      const preview = URL.createObjectURL(file);
      previews.current.add(preview);
      return { id: String(++photoSequence.current), file, preview };
    });
    setPhotos((current) => [...current, ...added]);
  }
  function movePhoto(index: number, direction: number) {
    setPhotos((current) => {
      const next = [...current];
      const target = index + direction;
      if (target < 0 || target >= next.length) return current;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }
  useEffect(() => {
    if (infoQuery.error) setError(infoQuery.error.message);
  }, [infoQuery.error]);
  return (
    <main className="capture-page">
      <Brand />
      <div className="capture-card">
        {done || info?.used ? (
          <>
            <div className="round-icon">
              <CheckCircle2 size={30} />
            </div>
            <h1>Pages delivered.</h1>
            <p>
              Your computer will take it from here. Keep this tab open or return
              to your book.
            </p>
            <p className="fine-print">
              Create a new link on your computer for the next batch.
            </p>
          </>
        ) : (
          <>
            <span className="eyebrow">A FEW PAGES, A LITTLE CLEARER</span>
            <h1>Bring your book.</h1>
            {info && (
              <p className="capture-book">
                <BookOpen size={17} />
                {info.book_title}
              </p>
            )}
            {error && (
              <div className="alert" role="alert">
                {error}
              </div>
            )}
            {info && (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  setBusy(true);
                  setError("");
                  try {
                    await uploadCaptureBatch(token, {
                      images: photos.map((photo) => photo.file),
                      page_labels: photos.map(
                        (photo, index) =>
                          photo.customLabel ??
                          `${startingPage + index * 2}–${startingPage + index * 2 + 1}`,
                      ),
                    });
                    setDone(true);
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <label className="phone-file">
                  <Smartphone size={27} />
                  <strong>Take a photograph</strong>
                  <span>Both pages, clear and in focus</span>
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    capture="environment"
                    disabled={busy || photos.length >= 10}
                    onChange={(event) => {
                      addPhotos(event.target.files);
                      event.target.value = "";
                    }}
                  />
                </label>
                <label className="phone-file capture-library">
                  <ImagePlus size={23} />
                  <strong>Choose from your photo library</strong>
                  <span>Select several photographs at once</span>
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    multiple
                    disabled={busy || photos.length >= 10}
                    onChange={(event) => {
                      addPhotos(event.target.files);
                      event.target.value = "";
                    }}
                  />
                </label>
                <label>
                  First page number
                  <input
                    type="number"
                    min={1}
                    max={100000}
                    required
                    value={startingPage}
                    disabled={busy}
                    onChange={(event) =>
                      setStartingPage(Number(event.target.value))
                    }
                  />
                </label>
                <div className="capture-photos">
                  {photos.map((photo, index) => (
                    <article className="capture-photo" key={photo.id}>
                      <img
                        src={photo.preview}
                        alt={`Photographed spread ${index + 1}`}
                      />
                      <div>
                        <label>
                          Pages
                          <input
                            aria-label={`Page numbers for photograph ${index + 1}`}
                            value={
                              photo.customLabel ??
                              `${startingPage + index * 2}–${startingPage + index * 2 + 1}`
                            }
                            maxLength={100}
                            disabled={busy}
                            onChange={(event) =>
                              setPhotos((current) =>
                                current.map((item) =>
                                  item.id === photo.id
                                    ? {
                                        ...item,
                                        customLabel: event.target.value,
                                      }
                                    : item,
                                ),
                              )
                            }
                          />
                        </label>
                        <div className="button-row">
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Move photograph ${index + 1} earlier`}
                            disabled={busy || index === 0}
                            onClick={() => movePhoto(index, -1)}
                          >
                            <ArrowUp size={17} />
                          </button>
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Move photograph ${index + 1} later`}
                            disabled={busy || index === photos.length - 1}
                            onClick={() => movePhoto(index, 1)}
                          >
                            <ArrowDown size={17} />
                          </button>
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Remove photograph ${index + 1}`}
                            disabled={busy}
                            onClick={() => {
                              URL.revokeObjectURL(photo.preview);
                              previews.current.delete(photo.preview);
                              setPhotos((current) =>
                                current.filter((item) => item.id !== photo.id),
                              );
                            }}
                          >
                            <X size={17} />
                          </button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
                <p className="fine-print">
                  {photos.length} photograph{photos.length === 1 ? "" : "s"} ·
                  Up to {photos.length * 2} pages. Check the order and page
                  labels before sending.
                </p>
                <button
                  className="button primary full-width"
                  disabled={busy || !photos.length}
                >
                  {busy ? <Spinner /> : <Upload size={17} />} Send to my reading
                  room
                </button>
                <p className="fine-print">
                  Up to 10 JPEG, PNG, or WebP photographs · Under 20 MB each and
                  80 MB total. OCR runs on your computer; extracted text is sent
                  to DeepInfra. Each spread uses AI credits. Your computer must
                  stay awake.
                </p>
              </form>
            )}
          </>
        )}
      </div>
      <p className="capture-footer">A little English, every day.</p>
    </main>
  );
}
