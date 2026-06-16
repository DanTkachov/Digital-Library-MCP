import json
from pathlib import Path

BOOK_FORMATS = {".pdf", ".epub", ".mobi", ".azw3", ".djvu", ".cbz", ".cbr", ".txt", ".docx"}


class LibraryState:
    def __init__(self, library_root: str, book_dump: str = "book_dump"):
        self.library_root = Path(library_root).resolve()
        self.book_dump = book_dump
        self.state_file = self.library_root / "library_state.json"
        self._data = {
            "library_root": str(self.library_root),
            "book_dump": book_dump,
            "not_categorized": [],
            "already_categorized": [],
            "category_list": [],
        }
        self._load()

    def _load(self) -> None:
        if self.state_file.exists():
            loaded = json.loads(self.state_file.read_text())
            for key in ("not_categorized", "already_categorized", "category_list"):
                self._data[key] = loaded.get(key, self._data[key])
            self._data["library_root"] = loaded.get("library_root", self._data["library_root"])
            self._data["book_dump"] = loaded.get("book_dump", self._data["book_dump"])

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._data, indent=2))

    def get_not_categorized(self) -> list[dict]:
        return list(self._data["not_categorized"])

    def get_already_categorized(self) -> list[dict]:
        return list(self._data["already_categorized"])

    def get_categories(self) -> list[str]:
        return list(self._data["category_list"])

    def add_books(self, paths: list[str]) -> int:
        existing = {b["path"] for b in self._data["not_categorized"]}
        existing |= {b["path"] for b in self._data["already_categorized"]}
        added = 0
        for path in paths:
            relative = str(Path(path).relative_to(self.library_root))
            if relative in existing:
                continue
            self._data["not_categorized"].append(
                {"path": relative, "title": Path(path).stem}
            )
            added += 1
        if added:
            self._save()
        return added

    def add_category(self, name: str) -> bool:
        if name in self._data["category_list"]:
            return False
        self._data["category_list"].append(name)
        self._data["category_list"].sort()
        self._save()
        return True

    def remove_from_not_categorized(self, book_path: str) -> bool:
        for i, b in enumerate(self._data["not_categorized"]):
            if b["path"] == book_path:
                self._data["not_categorized"].pop(i)
                self._save()
                return True
        return False

    def is_organized(self, book_path: str) -> bool:
        return any(b["path"] == book_path for b in self._data["already_categorized"])

    def set_category(self, book_path: str, category: str, moved_to: str) -> bool:
        nc = self._data["not_categorized"]
        for i, b in enumerate(nc):
            if b["path"] == book_path:
                entry = nc.pop(i)
                self._data["already_categorized"].append(
                    {
                        "path": book_path,
                        "title": entry["title"],
                        "category": category,
                        "moved_to": moved_to,
                    }
                )
                if category not in self._data["category_list"]:
                    self._data["category_list"].append(category)
                    self._data["category_list"].sort()
                self._save()
                return True
        return False

    def update_book_path(self, old_path: str, new_path: str) -> bool:
        for b in self._data["not_categorized"]:
            if b["path"] == old_path:
                b["path"] = new_path
                b["title"] = Path(new_path).stem
                self._save()
                return True
        for b in self._data["already_categorized"]:
            if b["path"] == old_path or b["moved_to"] == old_path:
                b["moved_to"] = new_path
                self._save()
                return True
        return False
