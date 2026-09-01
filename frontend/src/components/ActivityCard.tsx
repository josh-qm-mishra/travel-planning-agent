import type { Activity } from "@/lib/types";
import { formatTime, formatCost } from "@/utils/format";
import CategoryBadge from "./CategoryBadge";

export default function ActivityCard({ activity }: { activity: Activity }) {
  return (
    <div
      className={`relative rounded-xl border p-4 transition-shadow hover:shadow-md ${
        activity.locked
          ? "border-blue-200 bg-blue-50/40"
          : "border-gray-100 bg-white"
      }`}
    >
      {activity.locked && (
        <span
          title="Locked — will not change when replanning"
          className="absolute right-3 top-3 text-blue-400"
          aria-label="Locked activity"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4"
          >
            <path
              fillRule="evenodd"
              d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      )}

      <div className="flex items-start gap-3">
        <div className="mt-0.5 min-w-[5.5rem] text-xs font-medium text-gray-400 tabular-nums">
          {formatTime(activity.start_time)}
          <span className="mx-1">–</span>
          {formatTime(activity.end_time)}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-gray-900 leading-snug">
              {activity.name}
            </h3>
            <CategoryBadge category={activity.category} />
          </div>

          <p className="text-xs text-gray-500 mb-2 flex items-center gap-1">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="h-3 w-3 flex-shrink-0"
            >
              <path
                fillRule="evenodd"
                d="M9.69 18.933l.003.001C9.89 19.02 10 19 10 19s.11.02.308-.066l.002-.001.006-.003.018-.008a5.741 5.741 0 00.281-.14c.186-.096.446-.24.757-.433.62-.384 1.445-.966 2.274-1.765C15.302 14.988 17 12.493 17 9A7 7 0 103 9c0 3.492 1.698 5.988 3.355 7.584a13.731 13.731 0 002.273 1.765 11.842 11.842 0 00.976.544l.062.029.018.008.006.003zM10 11.25a2.25 2.25 0 100-4.5 2.25 2.25 0 000 4.5z"
                clipRule="evenodd"
              />
            </svg>
            {activity.location}
          </p>

          {activity.notes && (
            <p className="text-xs text-gray-500 italic mb-2">{activity.notes}</p>
          )}

          <div className="text-xs font-medium text-gray-700">
            {formatCost(activity.estimated_cost)}
          </div>
        </div>
      </div>
    </div>
  );
}
