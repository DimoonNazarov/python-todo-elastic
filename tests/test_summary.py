from app.services.summary import build_spacy_summary


def test_build_spacy_summary_returns_short_text():
    details = (
        "Отчёт по продажам нужен сегодня. Отчёт должен включать квартальные данные. "
        "Выделить ключевые отклонения и риски. "
        "Подготовить краткие выводы для команды."
    )
    summary = build_spacy_summary("Подготовить отчёт", details, max_sentences=2)

    assert summary
    # Выжимка короче исходного текста
    assert len(summary) < len(details)
    # Не более max_sentences предложений
    assert summary.count(".") <= 2
    # Наиболее значимое предложение попадает в выжимку
    assert "квартальные данные" in summary
    assert len(summary) > 60
