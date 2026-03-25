from app.services.summary import build_spacy_summary


def test_build_spacy_summary_returns_short_text_without_spacy_dependency():
    summary = build_spacy_summary(
        "Подготовить отчёт",
        (
            "Отчёт по продажам нужен сегодня. Отчёт должен включать квартальные данные. "
            "Выделить ключевые отклонения и риски. "
            "Подготовить краткие выводы для команды."
        ),
        max_sentences=2,
    )

    assert summary
    assert "Подготовить отчёт" in summary
    assert "Отчёт по продажам нужен сегодня." in summary
    assert "Подготовить краткие выводы для команды." not in summary
