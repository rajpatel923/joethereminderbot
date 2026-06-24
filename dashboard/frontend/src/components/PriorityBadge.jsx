const COLORS = {
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-green-100 text-green-700",
};

export default function PriorityBadge({ priority }) {
  const cls = COLORS[priority] || COLORS.medium;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>
      {priority}
    </span>
  );
}
