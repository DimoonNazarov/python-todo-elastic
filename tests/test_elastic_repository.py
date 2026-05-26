from types import SimpleNamespace

from app.repository.elastic_repository import create_russian_analyzer_mapping
from app.constants import ALL_STOPWORDS, CLASSIFICATION_REPLACEMENTS
from app.services import TodoClassificationService


def test_russian_analyzer_mapping_contains_classification_filters():
    mapping = create_russian_analyzer_mapping()
    analysis = mapping["settings"]["analysis"]

    analyzer = analysis["analyzer"]["russian_search_analyzer"]
    stop_filter = analysis["filter"]["russian_stop_with_group_names"]

    assert analyzer["tokenizer"] == "standard"
    assert "russian_stop_with_group_names" in analyzer["filter"]
    assert stop_filter["stopwords"] == ALL_STOPWORDS
    assert "александр" in stop_filter["stopwords"]
    assert "екатерина" in stop_filter["stopwords"]
    assert "дмитрий" in stop_filter["stopwords"]


def test_build_search_document_masks_secret_classification(
    classification_service: TodoClassificationService,
):
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

    document = classification_service.build_search_document(todo)

    assert document["classification_level"] == "совершенно секретно"
    assert document["masked_title"] == "не интерессно"
    assert "не интересно" in document["masked_details"]


def test_enrich_todo_display_adds_display_fields(
    classification_service: TodoClassificationService,
):
    todo = {
        "title": "совершенно секретно",
        "details": "особой важности",
        "classification_level": None,
    }

    enriched = classification_service.enrich(todo)

    assert enriched["display_title"] == "не интерессно"
    assert enriched["display_details"] == "не интересссно"


def test_detect_classification_osoboy_vazhnosti(
    classification_service: TodoClassificationService,
):
    assert (
        classification_service.detect("документ особой важности") == "особой важности"
    )


def test_detect_classification_sovershenno_sekretno(
    classification_service: TodoClassificationService,
):
    assert (
        classification_service.detect("гриф: совершенно секретно")
        == "совершенно секретно"
    )


def test_detect_classification_dsp(classification_service: TodoClassificationService):
    assert (
        classification_service.detect("для служебного пользования")
        == "для служебного пользования"
    )


def test_detect_classification_dsp_abbreviation(
    classification_service: TodoClassificationService,
):
    assert classification_service.detect("это дсп материал") == "дсп"


def test_detect_classification_sekretno(
    classification_service: TodoClassificationService,
):
    assert classification_service.detect("секретно") == "секретно"


def test_detect_classification_none_when_no_match(
    classification_service: TodoClassificationService,
):
    assert classification_service.detect("обычная задача") is None


def test_detect_classification_none_for_empty(
    classification_service: TodoClassificationService,
):
    assert classification_service.detect("") is None
    assert classification_service.detect(None) is None


# --- mask_classification ---


def test_mask_classification_replaces_sovershenno_sekretno(
    classification_service: TodoClassificationService,
):
    result = classification_service.mask("совершенно секретно документ")
    assert "совершенно секретно" not in result.lower()
    assert CLASSIFICATION_REPLACEMENTS["совершенно секретно"] in result


def test_mask_classification_case_insensitive(
    classification_service: TodoClassificationService,
):
    result = classification_service.mask("СОВЕРШЕННО СЕКРЕТНО")
    assert "совершенно секретно" not in result.lower()


def test_mask_classification_returns_text_unchanged_when_no_secret(
    classification_service: TodoClassificationService,
):
    text = "обычный текст задачи"
    assert classification_service.mask(text) == text


def test_mask_classification_none_input(
    classification_service: TodoClassificationService,
):
    assert classification_service.mask(None) is None

    # --- build_masked_fields ---


def test_build_masked_fields_detects_from_details(
    classification_service: TodoClassificationService,
):
    # гриф только в details
    result = classification_service.build_document_fields(
        "обычный заголовок", "совершенно секретно подробности"
    )
    assert result["classification_level"] == "совершенно секретно"
    assert result["masked_title"] == "обычный заголовок"  # заголовок не содержит гриф
    assert (
        CLASSIFICATION_REPLACEMENTS["совершенно секретно"] in result["masked_details"]
    )


def test_build_masked_fields_no_classification(
    classification_service: TodoClassificationService,
):
    result = classification_service.build_document_fields("купить молоко", "в магазине")
    assert result["classification_level"] is None
    assert result["masked_title"] is None
    assert result["masked_details"] is None


def test_build_masked_fields_none_details(
    classification_service: TodoClassificationService,
):
    result = classification_service.build_document_fields("совершенно секретно", None)
    assert result["classification_level"] == "совершенно секретно"
    assert result["masked_details"] is None

    # --- build_search_document ---


def test_build_search_document_structure(
    classification_service: TodoClassificationService,
):
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
    doc = classification_service.build_search_document(todo)
    assert doc["todo_id"] == 1
    assert doc["author_id"] == 2
    assert doc["title"] == "задача"
    assert doc["tag"] == "work"
    assert doc["completed"] is False
    assert "classification_level" in doc
    assert "masked_title" in doc


def test_build_search_document_no_classification(
    classification_service: TodoClassificationService,
):
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
    doc = classification_service.build_search_document(todo)
    assert doc["classification_level"] is None
    assert doc["masked_title"] is None

    # --- enrich_todo_display ---


def test_enrich_todo_display_with_dict(
    classification_service: TodoClassificationService,
):
    item = {"title": "секретно", "details": "инфо", "classification_level": None}
    result = classification_service.enrich(item)
    assert result["classification_level"] == "секретно"
    assert result["display_title"] == CLASSIFICATION_REPLACEMENTS["секретно"]


def test_enrich_todo_display_uses_existing_masked_fields(
    classification_service: TodoClassificationService,
):
    # Если masked_title уже проставлен — не пересчитывать
    item = {
        "title": "секретно",
        "details": None,
        "classification_level": "секретно",
        "masked_title": "уже замаскировано",
        "masked_details": None,
    }
    result = classification_service.enrich(item)
    assert result["display_title"] == "уже замаскировано"


def test_enrich_todo_display_sets_author_email_from_author(
    classification_service: TodoClassificationService,
):
    item = {
        "title": "задача",
        "details": None,
        "classification_level": None,
        "author": SimpleNamespace(email="user@test.com"),
        "author_email": None,
    }
    result = classification_service.enrich(item)
    assert result["author_email"] == "user@test.com"

    # --- merge_search_hits_with_todos ---


def test_merge_search_hits_skips_missing_todo(
    classification_service: TodoClassificationService,
):
    hits = [{"todo_id": 999, "_score": 1.0, "_id": "abc"}]
    todos = []
    result = classification_service.merge_search_hits_with_todos(hits, todos)
    assert result == []


def test_merge_search_hits_merges_correctly(
    classification_service: TodoClassificationService,
):
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
    result = classification_service.merge_search_hits_with_todos(hits, [todo])
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["author_email"] == "a@b.com"
    assert result[0]["_score"] == 0.9
