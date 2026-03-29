from types import SimpleNamespace

from app.repository.elastic_repository import create_russian_analyzer_mapping
from app.services.search_index import (
    ALL_STOPWORDS,
    detect_classification,
    mask_classification,
    merge_search_hits_with_todos,
    build_masked_fields,
)
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


def test_detect_classification_osoboy_vazhnosti():
    assert detect_classification("документ особой важности") == "особой важности"


def test_detect_classification_sovershenno_sekretno():
    assert detect_classification("гриф: совершенно секретно") == "совершенно секретно"


def test_detect_classification_dsp():
    assert detect_classification("для служебного пользования") == "дсп"


def test_detect_classification_dsp_abbreviation():
    assert detect_classification("это дсп материал") == "дсп"


def test_detect_classification_sekretno():
    assert detect_classification("секретно") == "секретно"


def test_detect_classification_none_when_no_match():
    assert detect_classification("обычная задача")


def test_detect_classification_none_for_empty():
    assert detect_classification("") is None
    assert detect_classification(None) is None


# --- mask_classification ---


def test_mask_classification_replaces_sovershenno_sekretno():
    result = mask_classification("совершенно секретно документ")
    assert "совершенно секретно" not in result.lower()
    assert CLASSIFICATION_REPLACEMENTS["совершенно секретно"] in result


def test_mask_classification_case_insensitive():
    result = mask_classification("СОВЕРШЕННО СЕКРЕТНО")
    assert "совершенно секретно" not in result.lower()


def test_mask_classification_returns_text_unchanged_when_no_secret():
    text = "обычный текст задачи"
    assert mask_classification(text) == text


def test_mask_classification_none_input():
    assert mask_classification(None) is None

    # --- build_masked_fields ---


def test_build_masked_fields_detects_from_details():
    # гриф только в details
    result = build_masked_fields("обычный заголовок", "совершенно секретно подробности")
    assert result["classification_level"] == "совершенно секретно"
    assert result["masked_title"] == "обычный заголовок"  # заголовок не содержит гриф
    assert (
        CLASSIFICATION_REPLACEMENTS["совершенно секретно"] in result["masked_details"]
    )


def test_build_masked_fields_no_classification():
    result = build_masked_fields("купить молоко", "в магазине")
    assert result["classification_level"] is None
    assert result["masked_title"] == "купить молоко"
    assert result["masked_details"] == "в магазине"


def test_build_masked_fields_none_details():
    result = build_masked_fields("совершенно секретно", None)
    assert result["classification_level"] == "совершенно секретно"
    assert result["masked_details"] is None

    # --- build_search_document ---


def test_build_search_document_structure():
    todo = SimpleNamespace(
        id=1,
        author_id=2,
        title="задача",
        details="описание",
        tag="work",
        created_at=None,
        updated_at=None,
        updated_by=None,
        completed=False,
        completed_at=None,
    )
    doc = build_search_document(todo)
    assert doc["todo_id"] == 1
    assert doc["author_id"] == 2
    assert doc["title"] == "задача"
    assert doc["tag"] == "work"
    assert doc["completed"] is False
    assert "classification_level" in doc
    assert "masked_title" in doc


def test_build_search_document_no_classification():
    todo = SimpleNamespace(
        id=5,
        author_id=1,
        title="обычная задача",
        details=None,
        tag=None,
        created_at=None,
        updated_at=None,
        updated_by=None,
        completed=True,
        completed_at=None,
    )
    doc = build_search_document(todo)
    assert doc["classification_level"] is None
    assert doc["masked_title"] == "обычная задача"

    # --- enrich_todo_display ---


def test_enrich_todo_display_with_dict():
    item = {"title": "секретно", "details": "инфо", "classification_level": None}
    result = enrich_todo_display(item)
    assert result["classification_level"] == "секретно"
    assert result["display_title"] == CLASSIFICATION_REPLACEMENTS["секретно"]


def test_enrich_todo_display_uses_existing_masked_fields():
    # Если masked_title уже проставлен — не пересчитывать
    item = {
        "title": "секретно",
        "details": None,
        "classification_level": "секретно",
        "masked_title": "уже замаскировано",
        "masked_details": None,
    }
    result = enrich_todo_display(item)
    assert result["display_title"] == "уже замаскировано"


def test_enrich_todo_display_sets_author_email_from_author():
    item = {
        "title": "задача",
        "details": None,
        "classification_level": None,
        "author": SimpleNamespace(email="user@test.com"),
        "author_email": None,
    }
    result = enrich_todo_display(item)
    assert result["author_email"] == "user@test.com"

    # --- merge_search_hits_with_todos ---


def test_merge_search_hits_skips_missing_todo():
    hits = [{"todo_id": 999, "_score": 1.0, "_id": "abc"}]
    todos = []
    result = merge_search_hits_with_todos(hits, todos)
    assert result == []


def test_merge_search_hits_merges_correctly():
    author = SimpleNamespace(email="a@b.com")
    todo = SimpleNamespace(
        id=1,
        author_id=10,
        author=author,
        title="задача",
        details="desc",
        tag="t",
        completed=False,
        created_at=None,
        completed_at=None,
        updated_at=None,
        updated_by=None,
        image_path=None,
    )
    hits = [
        {
            "todo_id": 1,
            "_score": 0.9,
            "_id": "x",
            "highlight": None,
            "classification_level": None,
            "masked_title": None,
            "masked_details": None,
        }
    ]
    result = merge_search_hits_with_todos(hits, [todo])
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["author_email"] == "a@b.com"
    assert result[0]["_score"] == 0.9
