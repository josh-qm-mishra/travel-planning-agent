import type { TripChangeSummary } from "@/lib/types";
import { formatDate, formatCost } from "@/utils/format";

function Stat({
  value,
  label,
  positive,
}: {
  value: number;
  label: string;
  positive?: boolean;
}) {
  if (value === 0) return null;
  const color = positive
    ? "text-green-700 bg-green-50"
    : "text-red-700 bg-red-50";
  return (
    <div
      className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium ${color}`}
    >
      <span className="text-base font-bold">{value}</span>
      <span className="font-normal opacity-80">{label}</span>
    </div>
  );
}

export default function ChangeSummary({
  summary,
}: {
  summary: TripChangeSummary;
}) {
  const hasChanges =
    summary.activities_added > 0 ||
    summary.activities_removed > 0 ||
    summary.activities_changed > 0;

  return (
    <div className="rounded-xl border border-green-200 bg-green-50 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="h-5 w-5 text-green-600 flex-shrink-0"
        >
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
            clipRule="evenodd"
          />
        </svg>
        <h3 className="text-sm font-semibold text-green-900">
          Trip updated
        </h3>
      </div>

      <p className="text-sm text-green-800">{summary.summary}</p>

      {hasChanges && (
        <div className="flex flex-wrap gap-2">
          <Stat
            value={summary.activities_added}
            label="added"
            positive={true}
          />
          <Stat value={summary.activities_removed} label="removed" />
          <Stat
            value={summary.activities_changed}
            label="changed"
            positive={true}
          />
        </div>
      )}

      {summary.budget_difference != null && summary.budget_difference !== 0 && (
        <p className="text-xs text-green-700">
          Budget difference:{" "}
          <span className="font-medium">
            {summary.budget_difference > 0 ? "+" : ""}
            {formatCost(summary.budget_difference)}
          </span>
        </p>
      )}

      {summary.affected_dates.length > 0 && (
        <div>
          <p className="text-xs text-green-700 font-medium mb-1">
            Affected dates:
          </p>
          <div className="flex flex-wrap gap-1.5">
            {summary.affected_dates.map((d) => (
              <span
                key={d}
                className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-800"
              >
                {formatDate(d)}
              </span>
            ))}
          </div>
        </div>
      )}

      {summary.locked_activities_changed > 0 && (
        <p className="text-xs text-amber-700 flex items-center gap-1">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 16 16"
            fill="currentColor"
            className="h-3 w-3"
          >
            <path
              fillRule="evenodd"
              d="M6.5 2.25a1.75 1.75 0 113.5 0v.5H6.5v-.5zM5 2.75v.5a1.75 1.75 0 00-1.75 1.75v7.5c0 .966.784 1.75 1.75 1.75h5.5A1.75 1.75 0 0012.25 12.5V5A1.75 1.75 0 0010.5 3.25v-.5A3.25 3.25 0 005 2.75z"
              clipRule="evenodd"
            />
          </svg>
          {summary.locked_activities_changed} locked{" "}
          {summary.locked_activities_changed === 1 ? "activity" : "activities"}{" "}
          changed
        </p>
      )}
    </div>
  );
}
