import type { BodyUploadReading } from "../../api/generated/models";
export function uploadBody(form: FormData): BodyUploadReading {
  const image = form.get("image");
  if (!(image instanceof Blob)) throw new Error("Choose a photograph first.");
  return { image, page_label: String(form.get("page_label") || "") };
}
