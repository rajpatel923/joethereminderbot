import { useEffect, useState } from "react";
import { api } from "../api";

export default function Notes() {
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newContent, setNewContent] = useState("");
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getNotes();
      setNotes(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    setCreating(true);
    try {
      await api.createNote({ content: newContent.trim() });
      setNewContent("");
      load();
    } catch (e) {
      alert(e.message);
    } finally {
      setCreating(false);
    }
  };

  const remove = async (note) => {
    if (!confirm("Delete this note?")) return;
    try {
      await api.deleteNote(note.id, note.user_id);
      load();
    } catch (e) {
      alert(e.message);
    }
  };

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-800 mb-4">Notes</h1>

      <form onSubmit={create} className="flex gap-2 mb-6">
        <input
          className="flex-1 border rounded px-3 py-1.5 text-sm"
          placeholder="Save a new fact to remember..."
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          required
        />
        <button
          type="submit"
          disabled={creating}
          className="px-4 py-1.5 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          Add
        </button>
      </form>

      {loading && <p className="text-gray-500 text-sm">Loading...</p>}
      {error && <p className="text-red-500 text-sm">{error}</p>}
      {!loading && !error && notes.length === 0 && (
        <p className="text-gray-400 text-sm">No notes saved yet.</p>
      )}
      <div className="space-y-2">
        {notes.map((n) => (
          <div
            key={n.id}
            className="bg-white rounded-lg shadow-sm border border-gray-200 px-4 py-3 flex items-start justify-between gap-3"
          >
            <div>
              <p className="text-gray-800 text-sm">{n.content}</p>
              <p className="text-xs text-gray-400 mt-0.5">
                {new Date(n.created_at).toLocaleDateString()}
              </p>
            </div>
            <button
              onClick={() => remove(n)}
              className="text-xs text-red-500 hover:text-red-700 flex-shrink-0"
            >
              Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
