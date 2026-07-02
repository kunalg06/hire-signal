import httpx
import json
from typing import Optional, List, Dict
from threading import Lock
from datetime import datetime

class Note:
    """Simple data holder for a note.

    Attributes
    ----------
    id: int
        Unique identifier assigned by the API.
    title: str
    content: str
    created_at: str  # ISO‑8601 timestamp
    tags: List[str]
    """

    def __init__(self, note_id: int, title: str, content: str, created_at: str, tags: Optional[List[str]] = None) -> None:
        self.id = note_id
        self.title = title
        self.content = content
        self.created_at = created_at
        # TODO: initialize the tags field, ensuring it defaults to an empty list when None is provided

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            # TODO: include the tags list in the serialized representation
        }

class NotesAPI:
    """In‑memory CRUD API for notes.

    The class is deliberately simple – it stores notes in a list and protects
    mutations with a threading.Lock to emulate basic concurrency safety.
    """

    def __init__(self) -> None:
        self._notes: List[Note] = []
        self._next_id: int = 1
        self._lock = Lock()

    # ---------- Helper methods ----------
    def _validate_tags(self, tags: Optional[List[str]]) -> List[str]:
        """Validate a list of tags.

        Returns a clean list of tags. Raises ValueError on any invalid entry.
        """
        if tags is None:
            return []
        # TODO: implement validation – each tag must be a non‑empty string without whitespace
        return tags

    def _find_note_index(self, note_id: int) -> int:
        for idx, note in enumerate(self._notes):
            if note.id == note_id:
                return idx
        return -1

    # ---------- CRUD operations ----------
    def create_note(self, title: str, content: str, tags: Optional[List[str]] = None) -> Dict:
        created_at = datetime.utcnow().isoformat() + "Z"
        clean_tags = self._validate_tags(tags)
        with self._lock:
            note = Note(self._next_id, title, content, created_at, clean_tags)
            self._notes.append(note)
            self._next_id += 1
        return note.to_dict()

    def get_note(self, note_id: int) -> Dict:
        idx = self._find_note_index(note_id)
        if idx == -1:
            raise KeyError(f"Note with id {note_id} not found")
        return self._notes[idx].to_dict()

    def update_note(self, note_id: int, title: Optional[str] = None, content: Optional[str] = None, tags: Optional[List[str]] = None) -> Dict:
        idx = self._find_note_index(note_id)
        if idx == -1:
            raise KeyError(f"Note with id {note_id} not found")
        with self._lock:
            note = self._notes[idx]
            if title is not None:
                note.title = title
            if content is not None:
                note.content = content
            if tags is not None:
                note.tags = self._validate_tags(tags)
        return note.to_dict()

    def delete_note(self, note_id: int) -> None:
        idx = self._find_note_index(note_id)
        if idx == -1:
            raise KeyError(f"Note with id {note_id} not found")
        with self._lock:
            self._notes.pop(idx)

    def list_notes(self, tags: Optional[List[str]] = None) -> List[Dict]:
        """Return all notes, optionally filtered by tags.

        If `tags` is provided, only notes that contain **all** of the supplied tags
        should be returned.
        """
        # TODO: implement tag‑based filtering using the helper `_validate_tags`
        return [note.to_dict() for note in self._notes]

if __name__ == "__main__":
    api = NotesAPI()
    n1 = api.create_note("Meeting notes", "Discuss project timeline", tags=["meeting", "project"])
    n2 = api.create_note("Grocery list", "Eggs, Milk, Bread")
    print("All notes:", json.dumps(api.list_notes(), indent=2))
    print("Filtered (meeting):", json.dumps(api.list_notes(tags=["meeting"]), indent=2))
    # Demonstrate error handling
    try:
        api.create_note("Bad", "Tag test", tags=["invalid tag"])
    except ValueError as e:
        print("Caught error:", e)
