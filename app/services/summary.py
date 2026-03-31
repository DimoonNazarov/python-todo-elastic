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


def _resolve_summary_sentences_count(details: str, max_sentences: int) -> int:
    if max_sentences > 1:
        return max_sentences

    sentences = _split_sentences(details)
    if len(details) > 260 or len(sentences) >= 3:
        return 2
    return 1


def _is_informative_sentence(sentence: str) -> bool:
    words = _extract_words(sentence)
    if len(words) < 4:
        return False
    if len(sentence.strip()) < 35:
        return False
    return True


def _finalize_summary(title: str | None, summary: str, max_chars: int = 320) -> str:
    summary = _remove_title_duplication(title, summary)
    return _trim_summary(summary, max_chars=max_chars)


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
    total_sentences = len(sentences)
    for index, sentence in enumerate(sentences):
        if not _is_informative_sentence(sentence):
            continue
        words = _extract_words(sentence)
        score = sum(frequencies.get(word, 0) for word in words)
        score += max(total_sentences - index, 0) * 0.5
        score += min(len(words), 18) * 0.2
        ranked_sentences.append((score, index, sentence))

    if not ranked_sentences:
        informative_sentences = [
            sentence for sentence in sentences if _is_informative_sentence(sentence)
        ]
        if informative_sentences:
            return " ".join(informative_sentences[:max_sentences])
        return " ".join(sentences[:max_sentences])

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

    resolved_max_sentences = _resolve_summary_sentences_count(details, max_sentences)
    nlp = get_russian_nlp()
    if nlp is None:
        summary = _build_regex_summary(source_text, resolved_max_sentences)
        return _finalize_summary(title, summary)

    doc = nlp(source_text)
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    if not sentences:
        return _trim_summary(source_text, max_chars=320)
    if len(sentences) <= resolved_max_sentences:
        summary = " ".join(sentences)
        return _finalize_summary(title, summary)

    frequencies = Counter()
    max_frequency = 1
    for token in doc:
        if token.is_space or token.is_punct or token.is_stop:
            continue
        lemma = (token.lemma_ or token.lower_).strip()
        if len(lemma) < 2:
            continue
        frequencies[lemma] += 1
        if frequencies[lemma] > max_frequency:
            max_frequency = frequencies[lemma]

    if not frequencies:
        summary = " ".join(sentences[:resolved_max_sentences])
        return _finalize_summary(title, summary)

    ranked_sentences = []
    total_sentences = len(sentences)
    for index, sent in enumerate(doc.sents):
        sentence_text = sent.text.strip()
        if not sentence_text:
            continue
        if not _is_informative_sentence(sentence_text):
            continue

        score = 0.0
        informative_tokens = 0
        for token in sent:
            if token.is_space or token.is_punct or token.is_stop:
                continue
            lemma = (token.lemma_ or token.lower_).strip()
            if len(lemma) < 2:
                continue
            score += frequencies.get(lemma, 0) / max_frequency
            informative_tokens += 1

        if informative_tokens == 0:
            continue

        score = score / informative_tokens
        score += max(total_sentences - index, 0) * 0.08
        score += min(informative_tokens, 18) * 0.04
        score += len(sent.ents) * 0.2
        if index == 0:
            score += 0.35
        elif index == 1:
            score += 0.2

        ranked_sentences.append((score, index, sentence_text))

    if not ranked_sentences:
        summary = _build_regex_summary(source_text, resolved_max_sentences)
        return _finalize_summary(title, summary)

    ranked_sentences.sort(key=lambda item: (-item[0], item[1]))
    selected = sorted(ranked_sentences[:resolved_max_sentences], key=lambda item: item[1])
    summary = " ".join(sentence for _, _, sentence in selected)
    return _finalize_summary(title, summary)
