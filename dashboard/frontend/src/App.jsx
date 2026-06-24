import { Routes, Route, NavLink } from "react-router-dom";
import Reminders from "./pages/Reminders";
import Notes from "./pages/Notes";
import History from "./pages/History";
import Settings from "./pages/Settings";

const navClass = ({ isActive }) =>
  `px-4 py-2 rounded text-sm font-medium transition-colors ${
    isActive
      ? "bg-indigo-600 text-white"
      : "text-gray-600 hover:bg-gray-100"
  }`;

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-2">
          <span className="font-bold text-gray-800 mr-4">Reminder Dashboard</span>
          <NavLink to="/" end className={navClass}>Reminders</NavLink>
          <NavLink to="/notes" className={navClass}>Notes</NavLink>
          <NavLink to="/history" className={navClass}>History</NavLink>
          <NavLink to="/settings" className={navClass}>Settings</NavLink>
        </div>
      </nav>
      <main className="max-w-5xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<Reminders />} />
          <Route path="/notes" element={<Notes />} />
          <Route path="/history" element={<History />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
