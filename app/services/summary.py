import importlib
import re
from collections import Counter
from functools import lru_cache


RUSSIAN_MODEL_CANDIDATES = (
    "ru_core_news_md",
    "ru_core_news_sm",
)


@lru_cache(maxsize=1)
def get_russian_nlp():
    try:
        spacy = importlib.import_module("spacy")
    except ImportError:
        return None

    for model_name in RUSSIAN_MODEL_CANDIDATES:
        try:
            return spacy.load(model_name)
        except OSError:
            continue

    nlp = spacy.blank("ru")
    if "sentencizer" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer")
    return nlp


def _normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _trim_summary(text: str, max_chars: int = 220) -> str:
    text = _normalize_text(text)
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars].rsplit(" ", 1)[0].strip(" ,;:-")
    return f"{truncated}..."


def _remove_title_duplication(title: str | None, summary: str) -> str:
    if not title or not summary:
        return summary

    normalized_title = _normalize_text(title).strip(' "\'«»').lower()
    normalized_summary = _normalize_text(summary)
    normalized_summary_plain = normalized_summary.strip(' "\'«»')

    if normalized_summary_plain.lower() == normalized_title:
        return normalized_summary

    for pattern in (
        rf'^\s*{re.escape(title)}\s*[:\-]\s*',
        rf'^\s*[«"]?{re.escape(title)}[»"]?\s*[:\-–—,]?\s*',
    ):
        normalized_summary = re.sub(pattern, "", normalized_summary, count=1, flags=re.IGNORECASE)

    return normalized_summary.strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _extract_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁё0-9-]{2,}", text.lower())


def _build_regex_summary(text: str, max_sentences: int) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return text[:280]
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    frequencies = Counter(_extract_words(text))
    if not frequencies:
        return " ".join(sentences[:max_sentences])

    ranked_sentences = []
    for index, sentence in enumerate(sentences):
        score = sum(frequencies.get(word, 0) for word in _extract_words(sentence))
        ranked_sentences.append((score, index, sentence))

    ranked_sentences.sort(key=lambda item: (-item[0], item[1]))
    selected = sorted(ranked_sentences[:max_sentences], key=lambda item: item[1])
    return " ".join(sentence for _, _, sentence in selected)


def build_spacy_summary(
    title: str | None,
    details: str | None,
    max_sentences: int = 1,
) -> str:
    title = _normalize_text(title or "")
    details = _normalize_text(details or "")
    source_text = details or title

    if not source_text:
        return ""

    nlp = get_russian_nlp()
    if nlp is None:
        summary = _build_regex_summary(source_text, max_sentences)
        summary = _remove_title_duplication(title, summary)
        return _trim_summary(summary)

    doc = nlp(source_text)
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    if not sentences:
        return _trim_summary(source_text, max_chars=220)
    if len(sentences) <= max_sentences:
        summary = " ".join(sentences)
        summary = _remove_title_duplication(title, summary)
        return _trim_summary(summary)

    frequencies = Counter()
    for token in doc:
        if token.is_space or token.is_punct or token.is_stop:
            continue
        lemma = (token.lemma_ or token.lower_).strip()
        if len(lemma) < 2:
            continue
        frequencies[lemma] += 1

    if not frequencies:
        summary = " ".join(sentences[:max_sentences])
        summary = _remove_title_duplication(title, summary)
        return _trim_summary(summary)

    ranked_sentences = []
    for index, sent in enumerate(doc.sents):
        sentence_text = sent.text.strip()
        if not sentence_text:
            continue

        score = 0
        for token in sent:
            if token.is_space or token.is_punct or token.is_stop:
                continue
            lemma = (token.lemma_ or token.lower_).strip()
            score += frequencies.get(lemma, 0)

        ranked_sentences.append((score, index, sentence_text))

    ranked_sentences.sort(key=lambda item: (-item[0], item[1]))
    selected = sorted(ranked_sentences[:max_sentences], key=lambda item: item[1])
    summary = " ".join(sentence for _, _, sentence in selected)
    summary = _remove_title_duplication(title, summary)
    return _trim_summary(summary)
