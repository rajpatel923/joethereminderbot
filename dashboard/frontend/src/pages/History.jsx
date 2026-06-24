import { useEffect, useState } from "react";
import { api } from "../api";
import PriorityBadge from "../components/PriorityBadge";
import CategoryTag from "../components/CategoryTag";

export default function History() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getHistory({ limit: 50 });
      setHistory(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const fmt = (iso) =>
    new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-gray-800">History</h1>
        <button onClick={load} className="text-sm text-indigo-600 hover:underline">Refresh</button>
      </div>

      {loading && <p className="text-gray-500 text-sm">Loading...</p>}
      {error && <p className="text-red-500 text-sm">{error}</p>}
      {!loading && !error && history.length === 0 && (
        <p className="text-gray-400 text-sm">No sent reminders yet.</p>
      )}
      <div className="space-y-2">
        {history.map((r) => (
          <div
            key={r.id}
            className="bg-white rounded-lg shadow-sm border border-gray-200 px-4 py-3"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1">
                <p className="text-gray-800 text-sm">{r.content}</p>
                <p className="text-xs text-gray-400 mt-0.5">{fmt(r.remind_at)}</p>
              </div>
              <div className="flex items-center gap-1">
                <PriorityBadge priority={r.priority} />
                <CategoryTag category={r.category} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
