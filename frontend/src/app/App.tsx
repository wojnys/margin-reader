import {
  ArrowRight,
  BookOpen,
  Bookmark,
  CheckCircle2,
  ChevronRight,
  Copy,
  GraduationCap,
  Leaf,
  MessageCircle,
  Plus,
  Settings,
  Sparkles,
  Wifi,
  X,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createBook } from "../api/generated/books/books";
import { pairPhone } from "../api/generated/capture/capture";
import type { PairingResponse } from "../api/generated/models";
import {
  correctReadingText,
  createSample,
  uploadReading,
} from "../api/generated/readings/readings";
import { saveExpression as saveExpressionRequest } from "../api/generated/vocabulary/vocabulary";
import { Brand } from "../components/layout/Brand";
import { ModalFrame } from "../components/ui/ModalFrame";
import { Spinner } from "../components/ui/Spinner";
import { bookInput } from "../features/books/bookInput";
import { uploadBody } from "../features/readings/uploadBody";
import { UploadForm } from "../features/readings/UploadForm";
import { useReadingRoom } from "../features/readings/useReadingRoom";
import { PracticePage } from "../pages/PracticePage";
import { ChatPage } from "../pages/ChatPage";
import { ReadingPage } from "../pages/ReadingPage";
import { VocabularyPage } from "../pages/VocabularyPage";
import type { Modal, Tab, View } from "./types";

export function App() {
  const [bookId, setBookId] = useState(
    localStorage.getItem("margin-book") || "",
  );
  const [readingId, setReadingId] = useState("");
  const [view, setView] = useState<View>("reading");
  const [tab, setTab] = useState<Tab>("summary");
  const [modal, setModal] = useState<Modal>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [pairing, setPairing] = useState<PairingResponse | null>(null);
  const knownReadings = useRef<string[]>([]);
  const close = useCallback(() => {
    setModal(null);
    setError("");
  }, []);

  const {
    books,
    vocabulary,
    readings,
    system,
    loading,
    queryError,
    refresh,
    setReadings,
    checkSystem,
  } = useReadingRoom(bookId);
  const book = books.find((b) => b.id === bookId);
  const reading = readings.find((r) => r.id === readingId);
  const due = vocabulary.filter((v) => new Date(v.due_at) <= new Date());
  useEffect(() => {
    if (queryError) setError(queryError.message);
  }, [queryError]);
  useEffect(() => {
    if (loading) return;
    setBookId((id) =>
      books.some((b) => b.id === id) ? id : books[0]?.id || "",
    );
  }, [books, loading]);
  useEffect(() => {
    localStorage.setItem("margin-book", bookId);
    setReadingId("");
    knownReadings.current = [];
  }, [bookId]);
  useEffect(() => {
    const isNew =
      knownReadings.current.length > 0 &&
      readings.some((r) => !knownReadings.current.includes(r.id));
    knownReadings.current = readings.map((r) => r.id);
    setReadingId((id) =>
      isNew || !readings.some((r) => r.id === id) ? readings[0]?.id || "" : id,
    );
  }, [readings]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 3500);
    return () => clearTimeout(timer);
  }, [toast]);

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function selectBook(id: string) {
    setBookId(id);
    setView("reading");
    setTab("summary");
  }
  async function sample() {
    await perform(async () => {
      const result = await createSample();
      await refresh();
      selectBook(result.book_id);
    });
  }
  async function openPhone() {
    if (!book) return;
    setPairing(null);
    setModal("phone");
    await perform(async () => {
      setPairing(await pairPhone(book.id));
    });
  }
  async function saveExpression(index: number) {
    if (!reading) return;
    await perform(async () => {
      await saveExpressionRequest({
        session_id: reading.id,
        revision: reading.revision,
        index,
      });
      const expression = reading.learning!.expressions[index].expression;
      setReadings((rs) =>
        rs.map((r) =>
          r.id === reading.id
            ? { ...r, saved_expressions: [...r.saved_expressions, expression] }
            : r,
        ),
      );
      await refresh();
      setToast("Saved to your expression library");
    });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand-link" aria-label="Margin home">
          <Brand />
        </a>
        <div className="sidebar-caption">A LITTLE ENGLISH, EVERY DAY</div>
        <nav className="primary-nav" aria-label="Main navigation">
          <button
            className={view === "chat" ? "nav-item selected" : "nav-item"}
            onClick={() => setView("chat")}
          >
            <MessageCircle size={19} /> Book chat
          </button>
          <button
            className={view === "reading" ? "nav-item selected" : "nav-item"}
            onClick={() => setView("reading")}
          >
            <BookOpen size={19} /> Reading room
          </button>
          <button
            className={view === "library" ? "nav-item selected" : "nav-item"}
            onClick={() => setView("library")}
          >
            <Bookmark size={19} /> My expressions{" "}
            <span className="nav-count">{vocabulary.length}</span>
          </button>
          <button
            className={view === "practice" ? "nav-item selected" : "nav-item"}
            onClick={() => setView("practice")}
          >
            <GraduationCap size={20} /> Practice{" "}
            {due.length > 0 && (
              <span className="nav-count green-count">{due.length}</span>
            )}
          </button>
        </nav>
        <div className="shelf-heading">
          <span>YOUR BOOKS</span>
          <button
            className="icon-button"
            aria-label="Add a book"
            onClick={() => setModal("book")}
          >
            <Plus size={17} />
          </button>
        </div>
        <div className="book-list">
          {books.map((b, i) => (
            <button
              key={b.id}
              className={`book-nav ${bookId === b.id && view === "reading" ? "active" : ""}`}
              onClick={() => selectBook(b.id)}
            >
              <span className={`mini-cover cover-${i % 3}`}>
                <BookOpen size={18} />
              </span>
              <span className="book-nav-text">
                <strong>{b.title}</strong>
                <small>{b.author || "Your next chapter"}</small>
              </span>
            </button>
          ))}
          {!books.length && (
            <p className="empty-shelf">
              Your next good read
              <br />
              belongs here.
            </p>
          )}
        </div>
        <button className="add-book-link" onClick={() => setModal("book")}>
          <Plus size={16} /> Add a book
        </button>
        <div className="sidebar-bottom">
          <div className="learner-card">
            <span className="learner-icon">
              <Leaf size={18} />
            </span>
            <div>
              <strong>Small steps. Real progress.</strong>
              <p>Make a few expressions yours.</p>
            </div>
          </div>
          <button
            className="nav-item settings-link"
            onClick={() => setModal("settings")}
          >
            <Settings size={18} /> Setup & connection
            <span
              className={`connection-dot ${system?.api_key_configured && system?.temporal_connected ? "connected" : ""}`}
            />
          </button>
        </div>
      </aside>
      <main className="main-content">
        <header className="topbar">
          <span className="breadcrumb">
            Your space <ChevronRight size={13} />{" "}
            {view === "reading"
              ? "Reading room"
              : view === "library"
                ? "My expressions"
                : view === "chat"
                  ? "Book chat"
                  : "Practice"}
          </span>
          <div className="language-pair">
            <span>EN</span>
            <ArrowRight size={13} />
            <span>ČEŠTINA</span>
          </div>
        </header>
        {books.length > 0 && view === "reading" && (
          <div className="mobile-book-switcher">
            <select
              aria-label="Choose your book"
              value={bookId}
              onChange={(e) => selectBook(e.target.value)}
            >
              {books.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.title}
                </option>
              ))}
            </select>
            <button
              className="button secondary"
              onClick={() => setModal("book")}
            >
              <Plus size={16} /> Add book
            </button>
          </div>
        )}
        {error && !modal && (
          <div role="alert" className="alert global-alert">
            {error}
            <button
              className="icon-button"
              aria-label="Dismiss error"
              onClick={() => setError("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {loading ? (
          <div className="loading-state">
            <Spinner /> Opening your reading room…
          </div>
        ) : view === "chat" ? (
          <ChatPage
            key={bookId}
            books={books}
            bookId={bookId}
            selectBook={setBookId}
            openReading={(id) => {
              setReadingId(id);
              setTab("source");
              setView("reading");
            }}
          />
        ) : view === "library" ? (
          <VocabularyPage
            vocabulary={vocabulary}
            practice={() => setView("practice")}
          />
        ) : view === "practice" ? (
          <PracticePage
            vocabulary={vocabulary}
            refresh={refresh}
            back={() => setView("library")}
          />
        ) : (
          <ReadingPage
            {...{
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
            }}
          />
        )}
        <footer className="app-footer">
          <span>Made for the way you read.</span>
          <span>
            ENGLISH IN CONTEXT <span className="footer-dot">·</span> CZECH AT
            HEART
          </span>
        </footer>
      </main>
      {toast && (
        <div role="status" className="toast">
          <CheckCircle2 size={18} />
          {toast}
        </div>
      )}
      {modal && (
        <ModalFrame
          title={
            modal === "book"
              ? "What are you reading?"
              : modal === "upload"
                ? "Bring a few pages."
                : modal === "phone"
                  ? "From your phone to your book."
                  : modal === "edit"
                    ? "Get the words right."
                    : "Your reading setup"
          }
          subtitle={
            modal === "book"
              ? "A little context helps every page make more sense."
              : modal === "upload"
                ? "Photograph both pages together, with the text in focus."
                : modal === "phone"
                  ? "Keep your phone and computer on the same Wi-Fi."
                  : modal === "edit"
                    ? "Correct both pages. The summaries and learning cards will be regenerated."
                    : undefined
          }
          close={close}
        >
          {error && (
            <div className="alert" role="alert">
              {error}
            </div>
          )}
          {modal === "book" && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                void perform(async () => {
                  const b = await createBook(bookInput(data));
                  await refresh();
                  selectBook(b.id);
                  close();
                });
              }}
            >
              <label>
                Book title
                <input
                  name="title"
                  required
                  maxLength={200}
                  placeholder="The book on your bedside table"
                />
              </label>
              <label>
                Author
                <input
                  name="author"
                  maxLength={200}
                  placeholder="Who wrote it?"
                />
              </label>
              <label>
                Your English level
                <select name="level" defaultValue="B2">
                  <option value="B1">B1 · Intermediate</option>
                  <option value="B2">B2 · Upper intermediate</option>
                  <option value="C1">C1 · Advanced</option>
                </select>
              </label>
              <label>
                Reading context <span className="optional">optional</span>
                <textarea
                  name="notes"
                  rows={3}
                  maxLength={4000}
                  placeholder="Characters, chapter, or anything you already know. Avoid later-page spoilers."
                />
              </label>
              <button disabled={busy} className="button primary full-width">
                {busy ? <Spinner /> : <BookOpen size={17} />} Create reading
                space
              </button>
            </form>
          )}
          {modal === "upload" && book && (
            <UploadForm
              busy={busy}
              onUpload={async (form) => {
                await perform(async () => {
                  const next = await uploadReading(book.id, uploadBody(form));
                  setReadings((rs) => [next, ...rs]);
                  setReadingId(next.id);
                  await refresh();
                  close();
                });
              }}
            />
          )}
          {modal === "phone" && (
            <>
              {pairing ? (
                <>
                  <div className="qr-wrap">
                    <QRCodeSVG
                      value={pairing.url}
                      size={190}
                      fgColor="#183f36"
                      marginSize={2}
                    />
                  </div>
                  <p className="center-text">
                    Scan with your phone’s camera.
                    <br />
                    <span className="muted">
                      Open the link, then take or choose several photos.
                    </span>
                  </p>
                  <div className="copy-link">
                    <input
                      aria-label="Phone upload link"
                      readOnly
                      value={pairing.url}
                    />
                    <button
                      className="icon-button"
                      aria-label="Copy upload link"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(pairing.url);
                          setToast("Upload link copied");
                        } catch {
                          setError("Select and copy the link manually.");
                        }
                      }}
                    >
                      <Copy size={17} />
                    </button>
                  </div>
                  <p className="fine-print center-text">
                    One batch of up to 10 photographs · Expires at{" "}
                    {new Date(pairing.expires_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                  <p className="fine-print">
                    If the phone cannot connect, allow the app through your
                    computer’s firewall and check the Wi-Fi network. You can
                    override the address with PHONE_BASE_URL in .env.
                  </p>
                </>
              ) : busy ? (
                <div className="loading-state">
                  <Spinner /> Creating your upload link…
                </div>
              ) : (
                <button className="button secondary" onClick={openPhone}>
                  Create a new upload link
                </button>
              )}
            </>
          )}
          {modal === "settings" && (
            <>
              <div className="setup-row">
                <span>
                  <Sparkles size={18} /> DeepInfra API key
                </span>
                <span
                  className={`status-pill ${system?.api_key_configured ? "ready" : ""}`}
                >
                  {system?.api_key_configured ? "Configured" : "Not configured"}
                </span>
              </div>
              <div className="setup-row">
                <span>
                  <Wifi size={18} /> Temporal service
                </span>
                <span
                  className={`status-pill ${system?.temporal_connected ? "ready" : ""}`}
                >
                  {system?.temporal_connected ? "Connected" : "Offline"}
                </span>
              </div>
              <div className="setup-note">
                <strong>Model</strong>
                <p>{system?.model || "Loading model…"}</p>
                <p className="muted">
                  Your key stays on the Python backend. Add it to the project’s
                  .env file as DEEPINFRA_API_KEY, then restart the API and
                  worker.
                </p>
                <p className="muted">
                  Photos and book text are sent to DeepInfra when you upload.
                  Your reading history and vocabulary are stored on this
                  computer.
                </p>
              </div>
              <button
                className="button secondary full-width"
                disabled={busy}
                onClick={() =>
                  perform(async () => {
                    await checkSystem();
                  })
                }
              >
                {busy ? <Spinner /> : <Wifi size={16} />} Check connection
              </button>
            </>
          )}
          {modal === "edit" && reading && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                void perform(async () => {
                  const next = await correctReadingText(reading.id, {
                    revision: reading.revision,
                    left: String(data.get("left") || ""),
                    right: String(data.get("right") || ""),
                  });
                  setReadings((rs) =>
                    rs.map((r) => (r.id === next.id ? next : r)),
                  );
                  close();
                });
              }}
            >
              <label>
                Left page
                <textarea
                  name="left"
                  rows={7}
                  defaultValue={reading.extraction?.left || ""}
                  required
                  maxLength={30000}
                />
              </label>
              <label>
                Right page
                <textarea
                  name="right"
                  rows={7}
                  defaultValue={reading.extraction?.right || ""}
                  required
                  maxLength={30000}
                />
              </label>
              <p className="fine-print">
                Previously saved expressions keep their original source.
                Regeneration makes new paid API requests.
              </p>
              <button className="button primary full-width" disabled={busy}>
                {busy ? <Spinner /> : <Sparkles size={17} />} Save & regenerate
              </button>
            </form>
          )}
        </ModalFrame>
      )}
    </div>
  );
}
