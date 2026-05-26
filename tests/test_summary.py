from app.services.summary import build_spacy_summary


def test_build_spacy_summary_returns_short_text():
    details = (
        "Отчёт по продажам нужен сегодня. Отчёт должен включать квартальные данные. "
        "Выделить ключевые отклонения и риски. "
        "Подготовить краткие выводы для команды."
    )
    summary = build_spacy_summary("Подготовить отчёт", details, max_sentences=2)

    assert summary
    assert len(summary) < len(details)
    assert summary.count(".") <= 2
    assert "квартальные данные" in summary
    assert len(summary) > 60
