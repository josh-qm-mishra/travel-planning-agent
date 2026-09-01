import { formatCategory } from "@/utils/format";

const categoryColors: Record<string, string> = {
  // backend-produced values
  museum: "bg-indigo-100 text-indigo-800",
  restaurant: "bg-amber-100 text-amber-800",
  cafe: "bg-amber-100 text-amber-800",
  bar: "bg-purple-100 text-purple-800",
  sightseeing: "bg-blue-100 text-blue-800",
  landmark: "bg-blue-100 text-blue-800",
  attraction: "bg-blue-100 text-blue-800",
  park: "bg-green-100 text-green-800",
  tour: "bg-cyan-100 text-cyan-800",
  transport: "bg-slate-100 text-slate-700",
  accommodation: "bg-purple-100 text-purple-800",
  hotel: "bg-purple-100 text-purple-800",
  shopping: "bg-pink-100 text-pink-800",
  outdoor: "bg-green-100 text-green-800",
  entertainment: "bg-orange-100 text-orange-800",
  culture: "bg-indigo-100 text-indigo-800",
  wellness: "bg-teal-100 text-teal-800",
  nightlife: "bg-violet-100 text-violet-800",
  food: "bg-amber-100 text-amber-800",
  food_and_drink: "bg-amber-100 text-amber-800",
  meal: "bg-amber-100 text-amber-800",
  "amusement center": "bg-orange-100 text-orange-800",
  amusement: "bg-orange-100 text-orange-800",
  activity: "bg-blue-100 text-blue-800",
};

export default function CategoryBadge({ category }: { category: string }) {
  const colorClass =
    categoryColors[category.toLowerCase()] ?? "bg-gray-100 text-gray-700";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colorClass}`}
    >
      {formatCategory(category)}
    </span>
  );
}
