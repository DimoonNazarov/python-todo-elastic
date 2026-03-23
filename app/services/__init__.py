__all__ = [
    "AuthService",
    "TodoService",
    "build_search_document",
    "detect_classification",
    "enrich_todo_display",
    "enrich_todo_display_list",
    "mask_classification",
    "merge_search_hits_with_todos",
]


def __getattr__(name: str):
    if name == "AuthService":
        from .auth import AuthService

        return AuthService
    if name == "TodoService":
        from .todo import TodoService

        return TodoService
    if name in {
        "build_search_document",
        "detect_classification",
        "enrich_todo_display",
        "enrich_todo_display_list",
        "mask_classification",
        "merge_search_hits_with_todos",
    }:
        from . import search_index

        return getattr(search_index, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
