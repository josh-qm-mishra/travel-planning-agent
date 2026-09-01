import type { TripDay } from "@/lib/types";
import { formatDate, formatCost } from "@/utils/format";
import ActivityCard from "./ActivityCard";

export default function DaySection({ day }: { day: TripDay }) {
  const totalCost = day.activities.reduce(
    (sum, a) => sum + a.estimated_cost,
    0,
  );

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-gray-800">
          {formatDate(day.date)}
        </h2>
        {totalCost > 0 && (
          <span className="text-xs text-gray-400 tabular-nums">
            {formatCost(totalCost)} total
          </span>
        )}
      </div>

      {day.activities.length === 0 ? (
        <p className="text-sm text-gray-400 italic py-4 text-center">
          No activities planned for this day.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {day.activities.map((activity, i) => (
            <ActivityCard key={`${activity.name}-${i}`} activity={activity} />
          ))}
        </div>
      )}
    </section>
  );
}
