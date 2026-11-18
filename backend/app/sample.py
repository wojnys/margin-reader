"""Original tutorial content, explicitly labelled and never charged as AI output."""

from __future__ import annotations

from pydantic import JsonValue

LEFT = """At the end of the platform, Anna caught sight of a small green notebook. She picked it up and looked around, but the station was almost empty.

She had been looking forward to this journey for weeks. Now, with the last train running late, she had plenty of time to spare. She opened the notebook. On the first page, someone had written: 'Pay attention to the things you usually take for granted.'"""
RIGHT = """Anna put her phone away. For a while, she listened to the rain on the station roof. It reminded her of summers at her grandmother's house.

When the train finally arrived, she was in no hurry to leave. She handed the notebook to the station attendant and stepped aboard. For once, the delay had given her something she needed."""


def expression(
    term: str,
    meaning: str,
    explanation: str,
    sentence: str,
    side: str,
    example: str,
    example_cs: str,
    kind: str = "phrase",
    level: str = "B2",
) -> dict[str, JsonValue]:
    return dict(
        expression=term,
        meaning_cs=meaning,
        explanation_cs=explanation,
        source_sentence=sentence,
        page_side=side,
        example_en=example,
        example_cs=example_cs,
        kind=kind,
        level=level,
    )


LEARNING: dict[str, JsonValue] = {
    "topic_title": "A Notebook Changes the Wait",
    "left_summary_en": "Anna is waiting for a late train when she notices a small green notebook. A message inside asks her to pay attention to ordinary things that she usually does not notice.",
    "right_summary_en": "Anna puts away her phone and listens to the rain. The quiet moment reminds her of childhood, so by the time the train arrives, the delay has given her something valuable.",
    "expressions": [
        expression(
            "catch sight of",
            "zahlédnout",
            "Někoho nebo něčeho si náhle všimnout. V textu je minulý tvar caught sight of.",
            "At the end of the platform, Anna caught sight of a small green notebook.",
            "left",
            "I caught sight of a fox near the river.",
            "U řeky jsem zahlédl lišku.",
            "collocation",
        ),
        expression(
            "look forward to",
            "těšit se na",
            "Po to následuje podstatné jméno nebo sloveso s koncovkou -ing.",
            "She had been looking forward to this journey for weeks.",
            "left",
            "I'm looking forward to reading the next chapter.",
            "Těším se na čtení další kapitoly.",
            "phrasal verb",
            "B1",
        ),
        expression(
            "time to spare",
            "čas navíc",
            "Čas, který zbývá po dokončení toho, co je třeba udělat.",
            "Now, with the last train running late, she had plenty of time to spare.",
            "left",
            "We arrived with ten minutes to spare.",
            "Dorazili jsme s desetiminutovou rezervou.",
            "collocation",
        ),
        expression(
            "take for granted",
            "považovat za samozřejmost",
            "Nevnímat dostatečně hodnotu něčeho, co máme běžně k dispozici.",
            "On the first page, someone had written: 'Pay attention to the things you usually take for granted.'",
            "left",
            "We often take clean water for granted.",
            "Čistou vodu často považujeme za samozřejmost.",
        ),
        expression(
            "in no hurry",
            "nespěchat",
            "Člověk necítí potřebu něco udělat rychle.",
            "When the train finally arrived, she was in no hurry to leave.",
            "right",
            "I'm in no hurry to finish this book.",
            "S dočtením této knihy nespěchám.",
            level="B1",
        ),
    ],
    "questions": [
        {
            "question_en": "What makes Anna change how she spends her waiting time?",
            "answer_cs": "Vzkaz v zápisníku ji vybídne, aby si všímala věcí, které běžně bere jako samozřejmost. Následně odloží telefon a poslouchá déšť.",
            "evidence_en": "Anna put her phone away.",
        },
        {
            "question_en": "Why might Anna feel differently about the delay at the end?",
            "answer_cs": "Text naznačuje, že jí čekání přineslo potřebnou chvíli klidu a vzpomínky na dětství. Jde o interpretaci podpořenou závěrečnou větou.",
            "evidence_en": "For once, the delay had given her something she needed.",
        },
    ],
}
