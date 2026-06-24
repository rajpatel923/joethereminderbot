import { useState } from "react";
import PriorityBadge from "./PriorityBadge";
import CategoryTag from "./CategoryTag";
import { api } from "../api";

export default function ReminderCard({ reminder, onRefresh }) {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(reminder.content);
  const [remindAt, setRemindAt] = useState(reminder.remind_at?.slice(0, 16) || "");
  const [snoozeMin, setSnoozeMin] = useState(30);
  const [busy, setBusy] = useState(false);

  const fmt = (iso) => {
    if (!iso) return "";
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  };

  const save = async () => {
    setBusy(true);
    try {
      await api.updateReminder(reminder.id, { content, remind_at: remindAt }, reminder.user_id);
      setEditing(false);
      onRefresh();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  };

  const remove = async () => {
    if (!confirm("Delete this reminder?")) return;
    setBusy(true);
    try {
      await api.deleteReminder(reminder.id, reminder.user_id);
      onRefresh();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  };

  const snooze = async () => {
    setBusy(true);
    try {
      await api.snoozeReminder(reminder.id, snoozeMin, reminder.user_id);
      onRefresh();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      {editing ? (
        <div className="space-y-2">
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <input
            type="datetime-local"
            className="border rounded px-2 py-1 text-sm"
            value={remindAt}
            onChange={(e) => setRemindAt(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              onClick={save}
              disabled={busy}
              className="px-3 py-1 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
            >
              Save
            </button>
            <button
              onClick={() => setEditing(false)}
              className="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <p className="text-gray-900 font-medium">{reminder.content}</p>
              <p className="text-xs text-gray-500 mt-0.5">{fmt(reminder.remind_at)}</p>
              {reminder.recurrence_rule && (
                <p className="text-xs text-gray-400 mt-0.5">Repeats: {reminder.recurrence_rule}</p>
              )}
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              <PriorityBadge priority={reminder.priority} />
              <CategoryTag category={reminder.category} />
            </div>
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button
              onClick={() => setEditing(true)}
              className="text-xs px-2 py-1 bg-gray-100 rounded hover:bg-gray-200"
            >
              Edit
            </button>
            <button
              onClick={remove}
              disabled={busy}
              className="text-xs px-2 py-1 bg-red-50 text-red-600 rounded hover:bg-red-100 disabled:opacity-50"
            >
              Delete
            </button>
            <div className="flex items-center gap-1 ml-auto">
              <input
                type="number"
                min="1"
                value={snoozeMin}
                onChange={(e) => setSnoozeMin(Number(e.target.value))}
                className="w-14 border rounded px-1 py-0.5 text-xs"
              />
              <span className="text-xs text-gray-500">min</span>
              <button
                onClick={snooze}
                disabled={busy}
                className="text-xs px-2 py-1 bg-yellow-50 text-yellow-700 rounded hover:bg-yellow-100 disabled:opacity-50"
              >
                Snooze
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
