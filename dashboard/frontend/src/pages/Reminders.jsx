import { useEffect, useState } from "react";
import { api } from "../api";
import ReminderCard from "../components/ReminderCard";

export default function Reminders() {
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterCategory, setFilterCategory] = useState("");
  const [filterPriority, setFilterPriority] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newTime, setNewTime] = useState("");
  const [newPriority, setNewPriority] = useState("medium");
  const [newCategory, setNewCategory] = useState("general");
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (filterCategory) params.category = filterCategory;
      if (filterPriority) params.priority = filterPriority;
      const data = await api.getReminders(params);
      setReminders(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filterCategory, filterPriority]);

  const create = async (e) => {
    e.preventDefault();
    if (!newContent.trim() || !newTime) return;
    setCreating(true);
    try {
      await api.createReminder({
        content: newContent.trim(),
        remind_at: new Date(newTime).toISOString(),
        priority: newPriority,
        category: newCategory,
      });
      setNewContent("");
      setNewTime("");
      setNewPriority("medium");
      setNewCategory("general");
      load();
    } catch (e) {
      alert(e.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-800 mb-4">Reminders</h1>

      {/* Create form */}
      <form onSubmit={create} className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6 space-y-3">
        <h2 className="text-sm font-semibold text-gray-700">New Reminder</h2>
        <input
          className="w-full border rounded px-3 py-1.5 text-sm"
          placeholder="What to remind about..."
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          required
        />
        <div className="flex gap-2 flex-wrap">
          <input
            type="datetime-local"
            className="border rounded px-2 py-1.5 text-sm"
            value={newTime}
            onChange={(e) => setNewTime(e.target.value)}
            required
          />
          <select
            className="border rounded px-2 py-1.5 text-sm"
            value={newPriority}
            onChange={(e) => setNewPriority(e.target.value)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
          <input
            className="border rounded px-2 py-1.5 text-sm w-32"
            placeholder="Category"
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
          />
          <button
            type="submit"
            disabled={creating}
            className="px-4 py-1.5 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            Add
          </button>
        </div>
      </form>

      {/* Filters */}
      <div className="flex gap-2 mb-4">
        <input
          className="border rounded px-2 py-1 text-sm w-36"
          placeholder="Filter category"
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
        />
        <select
          className="border rounded px-2 py-1 text-sm"
          value={filterPriority}
          onChange={(e) => setFilterPriority(e.target.value)}
        >
          <option value="">All priorities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <button onClick={load} className="text-sm text-indigo-600 hover:underline">Refresh</button>
      </div>

      {loading && <p className="text-gray-500 text-sm">Loading...</p>}
      {error && <p className="text-red-500 text-sm">{error}</p>}
      {!loading && !error && reminders.length === 0 && (
        <p className="text-gray-400 text-sm">No pending reminders.</p>
      )}
      <div className="space-y-3">
        {reminders.map((r) => (
          <ReminderCard key={r.id} reminder={r} onRefresh={load} />
        ))}
      </div>
    </div>
  );
}
