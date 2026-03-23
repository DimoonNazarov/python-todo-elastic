from types import SimpleNamespace

from app.repository.elastic_repository import create_russian_analyzer_mapping
from app.services.search_index import ALL_STOPWORDS
from app.services.search_index import CLASSIFICATION_REPLACEMENTS
from app.services.search_index import build_search_document
from app.services.search_index import enrich_todo_display


def test_russian_analyzer_mapping_contains_classification_filters():
    mapping = create_russian_analyzer_mapping()
    analysis = mapping["settings"]["analysis"]

    analyzer = analysis["analyzer"]["russian_search_analyzer"]
    stop_filter = analysis["filter"]["russian_stop_with_group_names"]
    char_filters = analysis["char_filter"]

    assert analyzer["tokenizer"] == "standard"
    assert "russian_stop_with_group_names" in analyzer["filter"]
    assert stop_filter["stopwords"] == ALL_STOPWORDS
    assert "александр" in stop_filter["stopwords"]
    assert "екатерина" in stop_filter["stopwords"]
    assert "дмитрий" in stop_filter["stopwords"]

    assert (
        char_filters["classification_sovershenno_sekretno"]["replacement"]
        == CLASSIFICATION_REPLACEMENTS["совершенно секретно"]
    )
    assert (
        char_filters["classification_osoboy_vazhnosti"]["replacement"]
        == CLASSIFICATION_REPLACEMENTS["особой важности"]
    )
    assert (
        char_filters["classification_sekretno"]["replacement"]
        == CLASSIFICATION_REPLACEMENTS["секретно"]
    )


def test_build_search_document_masks_secret_classification():
    todo = SimpleNamespace(
        id=7,
        title="совершенно секретно",
        details="Димон и Серега писали дсп документ",
        tag="Планы",
        created_at=None,
        updated_at=None,
        updated_by=None,
        completed=False,
        completed_at=None,
    )

    document = build_search_document(todo)

    assert document["classification_level"] == "совершенно секретно"
    assert document["masked_title"] == "не интерессно"
    assert "не интересно" in document["masked_details"]


def test_enrich_todo_display_adds_display_fields():
    todo = {
        "title": "совершенно секретно",
        "details": "особой важности",
        "classification_level": None,
    }

    enriched = enrich_todo_display(todo)

    assert enriched["display_title"] == "не интерессно"
    assert enriched["display_details"] == "не интересссно"
