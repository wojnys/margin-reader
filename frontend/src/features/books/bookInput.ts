import type { BookInput } from "../../api/generated/models";
export function bookInput(form: FormData): BookInput {
  const level = form.get("level");
  if (level !== "B1" && level !== "B2" && level !== "C1")
    throw new Error("Choose an English level.");
  return {
    title: String(form.get("title") || ""),
    author: String(form.get("author") || ""),
    notes: String(form.get("notes") || ""),
    level,
  };
}
