"""Manual paid integration check using only our original sample story."""

import asyncio
import json
import textwrap
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from backend.app.sample import LEFT, RIGHT


async def main():
    path = Path("data/qa-spread.jpg")
    image = Image.new("RGB", (1800, 1200), "#eee8d7")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=27)
    for side, text in enumerate((LEFT, RIGHT)):
        x = 65 + side * 900
        draw.rectangle((x - 30, 30, x + 800, 1170), fill="#fffdf4")
        y = 110
        for paragraph in text.split("\n\n"):
            for line in textwrap.wrap(paragraph, width=49):
                draw.text((x, y), line, font=font, fill="#262626")
                y += 43
            y += 40
        draw.text((x + 360, 1100), str(side + 1), font=font, fill="#888777")
    image.save(path, quality=95)
    async with httpx.AsyncClient(base_url="http://localhost:8017", timeout=20) as client:
        (await client.post("/api/bootstrap")).raise_for_status()
        books = (await client.get("/api/books")).json()
        book = next((b for b in books if b["author"] == "An original Margin sample"), None)
        if book is None:
            created = await client.post("/api/sample")
            created.raise_for_status()
            book = {"id": created.json()["book_id"]}
        with path.open("rb") as photo:
            response = await client.post(
                f"/api/books/{book['id']}/sessions",
                files={"image": ("sample-spread.jpg", photo, "image/jpeg")},
                data={"page_label": "Live API check"},
            )
        response.raise_for_status()
        reading_id = response.json()["id"]
        print(json.dumps({"session_id": reading_id, "status": "uploaded"}), flush=True)
        last = ""
        for _ in range(120):
            try:
                response = await client.get(f"/api/books/{book['id']}/sessions")
            except httpx.TransportError:
                print("API temporarily unreachable; the saved workflow continues independently.", flush=True)
                await asyncio.sleep(5)
                continue
            response.raise_for_status()
            reading = next(r for r in response.json() if r["id"] == reading_id)
            if reading["status"] != last:
                print(json.dumps({"status": reading["status"], "usage": reading["usage"]}), flush=True)
                last = reading["status"]
            if last in {"complete", "failed"}:
                print(
                    json.dumps(
                        {
                            "status": last,
                            "error": reading["error"],
                            "expressions": len(reading["learning"]["expressions"])
                            if reading["learning"]
                            else 0,
                            "questions": len(reading["learning"]["questions"]) if reading["learning"] else 0,
                            "usage": reading["usage"],
                        }
                    ),
                    flush=True,
                )
                return
            await asyncio.sleep(5)
        print("Check still running; inspect the reading room or Temporal UI.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
