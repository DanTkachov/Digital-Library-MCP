import os
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from fastmcp import FastMCP

from src.state import BOOK_FORMATS, LibraryState

EPUB_NS = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
}


class _TextStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text: list[str] = []

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def _strip_html(html: str) -> str:
    stripper = _TextStripper()
    stripper.feed(html)
    return " ".join(stripper.text)


def _extract_epub(path: Path, max_chars: int) -> str:
    text_parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        container = ElementTree.parse(zf.open("META-INF/container.xml"))
        rootfile_el = container.find(".//container:rootfile", EPUB_NS)
        if rootfile_el is None:
            return "[Error: could not find OPF in epub]"
        opf_path = rootfile_el.attrib["full-path"]

        opf = ElementTree.parse(zf.open(opf_path))
        opf_dir = os.path.dirname(opf_path)

        items: dict[str, str] = {}
        for item in opf.findall(".//opf:item", EPUB_NS):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            if item_id and href:
                items[item_id] = href

        spine = [
            ref.attrib.get("idref")
            for ref in opf.findall(".//opf:itemref", EPUB_NS)
        ]

        seen = set()
        for idref in spine:
            href = items.get(idref)
            if not href or href in seen:
                continue
            seen.add(href)
            try:
                content_path = os.path.normpath(os.path.join(opf_dir, href))
                html = zf.read(content_path).decode("utf-8", errors="ignore")
                stripped = _strip_html(html).strip()
                if stripped:
                    text_parts.append(stripped)
                    if sum(len(p) for p in text_parts) >= max_chars:
                        break
            except (KeyError, zipfile.BadZipFile):
                continue

    return " ".join(text_parts)[:max_chars]


def _extract_pdf(path: Path, max_chars: int) -> str:
    import fitz

    text_parts: list[str] = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            text = page.get_text().strip()
            if text:
                text_parts.append(text)
                if sum(len(p) for p in text_parts) >= max_chars:
                    break
    return " ".join(text_parts)[:max_chars]


def _extract_text_file(path: Path, max_chars: int) -> str:
    try:
        return path.read_text()[:max_chars]
    except Exception:
        return "[Error reading file]"


def _extract_preview(path: Path, max_chars: int) -> str:
    suffix = path.suffix.lower()
    if suffix == ".epub":
        try:
            return _extract_epub(path, max_chars)
        except Exception as e:
            return f"[Error parsing epub: {e}]"
    elif suffix == ".pdf":
        try:
            return _extract_pdf(path, max_chars)
        except Exception as e:
            return f"[Error parsing pdf: {e}]"
    elif suffix in {".txt", ".md", ".rst"}:
        return _extract_text_file(path, max_chars)
    else:
        return f"[Unsupported format for preview: {suffix}]"


def _scan_books(directory: Path) -> list[Path]:
    books: list[Path] = []
    if not directory.exists():
        return books
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.suffix.lower() in BOOK_FORMATS:
            books.append(entry)
    return books


def _is_hidden(name: str) -> bool:
    return name.startswith(".")


def create_server(library_root: str) -> FastMCP:
    state = LibraryState(library_root)
    library = state.library_root
    book_dump_dir = library / state.book_dump
    mcp = FastMCP("Digital Library")

    # Tool 1: List all Books
    @mcp.tool()
    def list_all_books() -> list[dict]:
        """List every book file in the library, with its organization status."""
        organized: dict[str, str] = {
            b["path"]: b["moved_to"] for b in state.get_already_categorized()
        }
        not_categorized: set[str] = {
            b["path"] for b in state.get_not_categorized()
        }
        result: list[dict] = []
        for entry in sorted(library.rglob("*")):
            if entry.is_file() and entry.suffix.lower() in BOOK_FORMATS:
                rel = str(entry.relative_to(library))
                if rel in organized:
                    status = "organized"
                    location = organized[rel]
                elif book_dump_dir in entry.parents and rel in not_categorized:
                    status = "pending"
                    location = ""
                elif book_dump_dir in entry.parents:
                    status = "unregistered"
                    location = ""
                else:
                    status = "organized"
                    location = str(entry.parent.relative_to(library))
                result.append(
                    {
                        "path": rel,
                        "title": entry.stem,
                        "format": entry.suffix.lower(),
                        "status": status,
                        "location": location,
                    }
                )
        return result

    # Tool 1.5: List book_dump
    @mcp.tool()
    def list_book_dump() -> list[dict]:
        """List unorganized books in the book dump folder. Syncs new files into state."""
        books = _scan_books(book_dump_dir)
        state.add_books([str(b) for b in books])
        not_categorized = state.get_not_categorized()
        result: list[dict] = []
        for b in not_categorized:
            full = library / b["path"]
            result.append(
                {
                    "path": b["path"],
                    "title": b["title"],
                    "format": full.suffix.lower() if full.exists() else "unknown",
                    "exists": full.exists(),
                }
            )
        return result

    # Tool 2: Create Directory
    @mcp.tool()
    def create_directory(name: str) -> str:
        """Create a new category directory in the library root."""
        if not name or "/" in name or "\\" in name:
            return f"Error: invalid category name '{name}'"
        target = library / name
        if target.exists():
            return f"Directory '{name}' already exists."
        target.mkdir(parents=True)
        state.add_category(name)
        return f"Created category directory '{name}'."

    # Tool 3: Book renaming
    @mcp.tool()
    def rename_book(book_path: str, new_name: str) -> str:
        """Rename a book file. book_path is relative to library root. new_name includes extension."""
        source = library / book_path
        if not source.exists():
            return f"Error: '{book_path}' does not exist."
        if "/" in new_name or "\\" in new_name:
            return "Error: new_name must be a filename, not a path."
        dest = source.with_name(new_name)
        if dest.exists():
            return f"Error: '{new_name}' already exists in that directory."
        old_rel = str(source.relative_to(library))
        new_rel = str(dest.relative_to(library))
        source.rename(dest)
        state.update_book_path(old_rel, new_rel)
        return f"Renamed '{old_rel}' -> '{new_rel}'."

    # Tool 4: Move book from one dir to another
    @mcp.tool()
    def move_book(book_path: str, category: str) -> str:
        """Move a book from book dump into a category folder. Updates state automatically."""
        source = library / book_path
        if state.is_organized(book_path):
            return f"Error: '{book_path}' is already organized."
        if not source.exists():
            return f"Error: '{book_path}' does not exist."
        cat_dir = library / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        dest = cat_dir / source.name
        if dest.exists():
            return f"Error: '{dest.relative_to(library)}' already exists."
        source.rename(dest)
        new_rel = str(dest.relative_to(library))
        state.set_category(book_path, category, new_rel)
        state.add_category(category)
        return f"Moved '{book_path}' -> '{new_rel}' (category: {category})."

    # Tool 5: book preview; get the first 2000 chars of a book to categorize it
    @mcp.tool()
    def preview_book(book_path: str, chars: int = 2000) -> str:
        """Extract first N chars of a book for categorization. Supports PDF, EPUB, plain text."""
        source = library / book_path
        if not source.exists():
            return f"Error: '{book_path}' does not exist."
        return _extract_preview(source, chars)

    # Tool 6: List categories; agent should try to organize into existing categories first
    @mcp.tool()
    def list_categories() -> list[str]:
        """List existing category directories in the library, sorted alphabetically."""
        cats: list[str] = []
        if not library.exists():
            return cats
        for entry in sorted(library.iterdir()):
            if entry.is_dir() and not _is_hidden(entry.name) and entry.name != state.book_dump:
                cats.append(entry.name)
        return cats

    return mcp


def main() -> None:
    library_root = sys.argv[1] if len(sys.argv) > 1 else os.getenv("LIBRARY_ROOT", os.getcwd())
    if not Path(library_root).exists():
        print(f"Error: library root '{library_root}' does not exist.", file=sys.stderr)
        sys.exit(1)
    create_server(library_root).run()


if __name__ == "__main__":
    main()
