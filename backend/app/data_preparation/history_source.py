"""Explicit history allowlist, separate from the catalog export registry."""
from pathlib import Path
from .source import _read_selected_table

HISTORY_EXPORT_COLUMNS = {
    "CourseUserBindings": ("Id", "CourseId", "UserId", "IsCompleted", "Completed", "LessonsCompleted",
        "IsPaid", "SubscriptionId", "Created", "ContentAccess", "BuyingDate", "Modified", "Status",
        "StudyingStartDate", "IsDeleted", "StreamId"),
    "CourseUserLessonBindings": ("Id", "CourseUserId", "LessonId", "Completed", "Created", "StudyingStartDate"),
    "UserRatings": ("Id", "Value", "UserId", "EntityId", "EntityTypeId", "Created", "Modified", "IsDeleted"),
    "UserRatingTagsBindings": ("UserRatingId", "TagId", "Text"),
    "Ratings": ("Id", "Value", "RatingGroupId", "Question", "IsDeleted"),
    "RatingGroups": ("Id", "Title", "Question", "IsDeleted"),
    "RatingTags": ("Id", "Title", "IsDeleted", "IsSystem"),
    "RatingTagBindings": ("RatingId", "TagId", "Order"),
    "RecommendedItems": ("Id", "ItemId", "ItemTypeId", "CreatedAtUtc", "Order", "CourseId"),
    "Lessons": ("Id", "IsDeleted", "IsGroup", "RatingGroupId"),
    "Courses": ("Id", "IsDeleted", "IsClosed", "LessonQuantity", "AutoOpenNextLesson", "PassageMode"),
    "CourseLessonBindings": ("Id", "CourseId", "LessonId", "Order", "ParentGroupId", "IsTrial", "IsClosed", "ClosedUntil"),
    "Calculators": ("Id", "IsDeleted", "RatingGroupId"),
    "CalculatorPages": ("Id", "IsDeleted", "RatingGroupId"),
    "Articles": ("Id", "IsDeleted", "RatingGroupId"),
}
PRIMARY_SOURCES = ("CourseUserBindings", "CourseUserLessonBindings", "UserRatings")

def read_history_table(table_name: str, compose_file: Path):
    if table_name not in HISTORY_EXPORT_COLUMNS:
        raise ValueError(f"History table is not allowed: {table_name}")
    return _read_selected_table(table_name, HISTORY_EXPORT_COLUMNS[table_name], compose_file)
