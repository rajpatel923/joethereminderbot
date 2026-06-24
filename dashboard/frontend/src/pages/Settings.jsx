import { useEffect, useState } from "react";
import { api } from "../api";

export default function Settings() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState({});
  const [saving, setSaving] = useState({});

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getUsers();
      setUsers(data);
      const initial = {};
      data.forEach((u) => { initial[u.id] = u.timezone; });
      setEditing(initial);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const saveTz = async (userId) => {
    setSaving((s) => ({ ...s, [userId]: true }));
    try {
      await api.updateTimezone(userId, editing[userId]);
      alert("Timezone updated!");
    } catch (e) {
      alert(e.message);
    } finally {
      setSaving((s) => ({ ...s, [userId]: false }));
    }
  };

  return (
    <div>
      <h1 className="text-xl font-bold text-gray-800 mb-4">Settings</h1>

      {loading && <p className="text-gray-500 text-sm">Loading...</p>}
      {error && <p className="text-red-500 text-sm">{error}</p>}
      {!loading && !error && users.length === 0 && (
        <p className="text-gray-400 text-sm">No users yet. Send a message to your bot to register.</p>
      )}

      <div className="space-y-4">
        {users.map((u) => (
          <div key={u.id} className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm font-semibold text-gray-800">User #{u.id}</p>
                <p className="text-xs text-gray-400">Telegram ID: {u.telegram_id}</p>
                <p className="text-xs text-gray-400">Joined: {new Date(u.created_at).toLocaleDateString()}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-600 w-24">Timezone:</label>
              <input
                className="border rounded px-2 py-1 text-sm flex-1"
                value={editing[u.id] || ""}
                onChange={(e) =>
                  setEditing((prev) => ({ ...prev, [u.id]: e.target.value }))
                }
                placeholder="e.g. America/Chicago"
              />
              <button
                onClick={() => saveTz(u.id)}
                disabled={saving[u.id]}
                className="px-3 py-1 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
