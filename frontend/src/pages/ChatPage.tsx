import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BookOpen, MessageCircle, Plus, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  createBookChat,
  getBookChat,
  listBookChats,
  retryBookChatMessage,
  sendBookChatMessage,
} from "../api/generated/chat/chat";
import type { BookResponse } from "../api/generated/models";
import { Spinner } from "../components/ui/Spinner";
import { KnowledgePanel } from "../features/knowledge/KnowledgePanel";

interface Props {
  books: BookResponse[];
  bookId: string;
  selectBook: (id: string) => void;
  openReading: (id: string) => void;
}

const active = new Set(["pending", "queued", "generating"]);

export function ChatPage({ books, bookId, selectBook, openReading }: Props) {
  const queryClient = useQueryClient();
  const [threadId, setThreadId] = useState("");
  const [pageStart, setPageStart] = useState("");
  const [pageEnd, setPageEnd] = useState("");
  const [question, setQuestion] = useState("");
  const request = useRef<{
    thread: string;
    question: string;
    id: string;
  } | null>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setThreadId("");
    setQuestion("");
    request.current = null;
  }, [bookId]);
  const threads = useQuery({
    queryKey: ["book-chats", bookId],
    queryFn: () => listBookChats(bookId),
    enabled: !!bookId,
  });
  const detail = useQuery({
    queryKey: ["book-chat", threadId],
    queryFn: () => getBookChat(threadId),
    enabled: !!threadId,
    refetchInterval: (query) =>
      query.state.data?.turns.some((turn) => active.has(turn.status))
        ? 2000
        : false,
  });
  const waiting =
    detail.data?.turns.some((turn) => active.has(turn.status)) ?? false;
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [detail.data?.turns.length, waiting]);

  async function invalidate(id: string) {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["book-chat", id] }),
      queryClient.invalidateQueries({ queryKey: ["book-chats", bookId] }),
    ]);
  }

  const send = useMutation({
    mutationFn: async () => {
      let id = threadId;
      if (!id) {
        const thread = await createBookChat(bookId, { language: "en" });
        id = thread.id;
        setThreadId(id);
      }
      const text = question.trim();
      const requestKey = `${text}|${pageStart}|${pageEnd}`;
      if (
        !request.current ||
        request.current.thread !== id ||
        request.current.question !== requestKey
      ) {
        request.current = {
          thread: id,
          question: requestKey,
          id: crypto.randomUUID(),
        };
      }
      await sendBookChatMessage(id, {
        question: text,
        request_id: request.current.id,
        page_start: pageStart ? Number(pageStart) : undefined,
        page_end: pageEnd ? Number(pageEnd) : undefined,
      });
      request.current = null;
      setQuestion("");
      await invalidate(id);
    },
  });
  const retry = useMutation({
    mutationFn: async (turnId: string) => {
      await retryBookChatMessage(threadId, turnId);
      await invalidate(threadId);
    },
  });
  const busy = waiting || send.isPending || retry.isPending;
  const error = send.error || retry.error || detail.error || threads.error;
  const selectedBook = books.find((book) => book.id === bookId);

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">A LITTLE CLARITY, BETWEEN THE LINES</div>
          <h1>Talk about your book.</h1>
          <p>
            Ask about your uploaded pages. Replies are always in clear English.
          </p>
        </div>
      </div>
      {!books.length ? (
        <section className="empty-reading">
          <BookOpen size={30} />
          <h2>Start with a book.</h2>
          <p>
            Add a book in your reading room and upload some pages to begin a
            conversation.
          </p>
        </section>
      ) : (
        <>
          <div className="chat-book-bar">
            <label>
              YOUR BOOK
              <select
                aria-label="Choose a book to chat about"
                value={bookId}
                disabled={busy}
                onChange={(event) => selectBook(event.target.value)}
              >
                {books.map((book) => (
                  <option key={book.id} value={book.id}>
                    {book.title}
                  </option>
                ))}
              </select>
            </label>
            <span className="fine-print">
              Uses this book's uploaded pages. Set a last page below to exclude
              later material.
            </span>
          </div>
          <KnowledgePanel
            key={bookId}
            bookId={bookId}
            openReading={openReading}
          />
          <div className="book-chat-layout">
            <aside className="chat-history" aria-label="Saved conversations">
              <button
                className="button secondary"
                disabled={send.isPending}
                onClick={() => {
                  setThreadId("");
                  setQuestion("");
                  send.reset();
                  retry.reset();
                }}
              >
                <Plus size={16} /> New conversation
              </button>
              <span className="small-label">SAVED CONVERSATIONS</span>
              {threads.isPending ? (
                <Spinner />
              ) : threads.data?.length ? (
                threads.data.map((thread) => (
                  <button
                    key={thread.id}
                    className={`chat-thread ${thread.id === threadId ? "selected" : ""}`}
                    disabled={send.isPending}
                    onClick={() => {
                      setThreadId(thread.id);
                      setQuestion("");
                      send.reset();
                      retry.reset();
                    }}
                  >
                    <MessageCircle size={16} />
                    <span>
                      <strong>{thread.title}</strong>
                      <small>
                        English replies ·{" "}
                        {new Date(thread.created_at).toLocaleDateString()}
                      </small>
                    </span>
                  </button>
                ))
              ) : (
                <p className="muted">Your conversations will be saved here.</p>
              )}
            </aside>
            <section className="book-chat-panel" aria-label="Book conversation">
              <header className="chat-panel-heading">
                <BookOpen size={20} />
                <div>
                  <strong>{selectedBook?.title}</strong>
                  <p>
                    {detail.data?.title ||
                      "A question is a good place to start."}
                  </p>
                </div>
                <span className="fine-print">English replies</span>
              </header>
              <div
                className="chat-messages"
                role="log"
                aria-label="Messages"
                aria-live="polite"
              >
                {detail.isLoading && threadId ? (
                  <Spinner />
                ) : !detail.data?.turns.length ? (
                  <div className="chat-welcome">
                    <MessageCircle size={32} />
                    <h2>What would you like to understand?</h2>
                    <p>
                      Your question can draw on all the pages you have uploaded
                      for this book. Answers include supporting passages when
                      the text supports them.
                    </p>
                    <div className="chat-suggestions">
                      {[
                        "Explain the main events in my uploaded pages.",
                        "Which expressions could I use at work?",
                        "Explain a useful grammar pattern from these pages.",
                      ].map((suggestion) => (
                        <button
                          key={suggestion}
                          type="button"
                          onClick={() => setQuestion(suggestion)}
                        >
                          {suggestion}
                          <ArrowRight size={14} />
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  detail.data.turns.map((turn) => (
                    <div className="chat-turn" key={turn.id}>
                      <div className="chat-question">
                        <span className="small-label">YOU</span>
                        <p>{turn.question}</p>
                      </div>
                      <div className="chat-answer">
                        <span className="small-label">MARGIN</span>
                        {active.has(turn.status) ? (
                          <p role="status" className="chat-working">
                            <Spinner />
                            {turn.status === "generating"
                              ? "Reading your passages and preparing a reply…"
                              : "Question saved. Waiting for the reading worker…"}{" "}
                            You can come back later.
                          </p>
                        ) : turn.status === "failed" ? (
                          <div className="alert">
                            <p>{turn.error}</p>
                            <button
                              className="button small secondary"
                              disabled={busy}
                              onClick={() => retry.mutate(turn.id)}
                            >
                              Retry reply · uses AI credits
                            </button>
                          </div>
                        ) : (
                          turn.answer && (
                            <>
                              {!turn.answer.supported && (
                                <span className="subtle-tag">
                                  The supplied passages do not establish an
                                  answer
                                </span>
                              )}
                              <div className="chat-answer-text" lang="en">
                                {turn.answer.answer}
                              </div>
                              {turn.answer.citations.map((citation, index) => {
                                const source = turn.sources.find(
                                  (item) => item.id === citation.source_id,
                                );
                                return source ? (
                                  <details
                                    className="chat-citation"
                                    key={`${citation.source_id}-${index}`}
                                  >
                                    <summary>
                                      <BookOpen size={14} />{" "}
                                      {source.kind === "summary"
                                        ? "Generated recap of pages "
                                        : "Pages "}
                                      {source.page_label || "unlabelled"} ·{" "}
                                      {source.kind !== "summary"
                                        ? `${source.side} page · `
                                        : ""}
                                      Source {index + 1}
                                    </summary>
                                    {source.kind === "summary" && (
                                      <p className="fine-print">
                                        Generated summary, not the author's
                                        original wording.
                                      </p>
                                    )}
                                    <blockquote lang="en">
                                      “{citation.quote}”
                                    </blockquote>
                                    <p className="fine-print">
                                      Saved source snapshot · revision{" "}
                                      {source.revision}. Original text may have
                                      been corrected since this reply.
                                    </p>
                                    <details>
                                      <summary>
                                        Read the supporting passage
                                      </summary>
                                      <p className="chat-source-text" lang="en">
                                        {source.text}
                                      </p>
                                    </details>
                                    <button
                                      type="button"
                                      className="text-button"
                                      onClick={() =>
                                        openReading(source.session_id)
                                      }
                                    >
                                      Open original reading{" "}
                                      <ArrowRight size={14} />
                                    </button>
                                  </details>
                                ) : null;
                              })}
                              <p className="fine-print">
                                Retrieval:{" "}
                                {turn.retrieval_strategy ||
                                  "saved source snapshot"}
                                .{" "}
                                {turn.sources.length < turn.source_count
                                  ? `${turn.sources.length} relevant excerpts selected from ${turn.source_count} across your uploaded pages. Answers may miss details; ask about a specific event or phrase to refine the search.`
                                  : "Based on available extracted text from this book."}{" "}
                                Estimated AI cost $
                                {turn.estimated_cost.toFixed(4)} USD
                              </p>
                              {turn.retrieval_notes?.map((note, index) => (
                                <p className="fine-print" key={index}>
                                  {note}
                                </p>
                              ))}
                            </>
                          )
                        )}
                      </div>
                    </div>
                  ))
                )}
                <div ref={end} />
              </div>
              {error && (
                <div className="alert" role="alert">
                  {error.message}
                </div>
              )}
              <form
                className="chat-composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (question.trim() && !busy) send.mutate();
                }}
              >
                <div className="chat-page-scope">
                  <label>
                    From page
                    <input
                      type="number"
                      min="1"
                      value={pageStart}
                      onChange={(e) => setPageStart(e.target.value)}
                      disabled={busy}
                      placeholder="All"
                    />
                  </label>
                  <label>
                    Through page
                    <input
                      type="number"
                      min="1"
                      value={pageEnd}
                      onChange={(e) => setPageEnd(e.target.value)}
                      disabled={busy}
                      placeholder="Latest uploaded"
                    />
                  </label>
                </div>
                <label className="sr-only" htmlFor="book-chat-question">
                  Your question about the book
                </label>
                <textarea
                  id="book-chat-question"
                  placeholder="Ask about a scene, an expression, or a grammar pattern…"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  maxLength={4000}
                  rows={3}
                  disabled={busy}
                />
                <div>
                  <span className="fine-print">
                    Saved conversations · Each reply uses AI credits · AI can
                    make mistakes.
                  </span>
                  <button
                    className="button primary"
                    disabled={busy || !question.trim() || !bookId}
                    type="submit"
                  >
                    {send.isPending ? <Spinner /> : <Send size={16} />} Send
                  </button>
                </div>
              </form>
            </section>
          </div>
        </>
      )}
    </>
  );
}
