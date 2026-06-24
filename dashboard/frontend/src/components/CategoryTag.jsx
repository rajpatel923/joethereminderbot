export default function CategoryTag({ category }) {
  if (!category || category === "general") return null;
  return (
    <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 font-medium">
      {category}
    </span>
  );
}
