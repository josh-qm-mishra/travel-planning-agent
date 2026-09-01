import type { TripPreferences } from "@/lib/types";
import { formatPace, formatWalkingTolerance } from "@/utils/format";

function Pill({ label }: { label: string }) {
  return (
    <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-700">
      {label}
    </span>
  );
}

export default function TripPreferencesSummary({
  preferences,
}: {
  preferences: TripPreferences;
}) {
  return (
    <div className="space-y-3 text-sm">
      {preferences.interests.length > 0 && (
        <div>
          <span className="text-xs font-medium uppercase tracking-wide text-gray-400 block mb-1.5">
            Interests
          </span>
          <div className="flex flex-wrap gap-1.5">
            {preferences.interests.map((t) => (
              <Pill key={t} label={t} />
            ))}
          </div>
        </div>
      )}

      {preferences.food_preferences.length > 0 && (
        <div>
          <span className="text-xs font-medium uppercase tracking-wide text-gray-400 block mb-1.5">
            Food
          </span>
          <div className="flex flex-wrap gap-1.5">
            {preferences.food_preferences.map((t) => (
              <Pill key={t} label={t} />
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-4 text-xs text-gray-600">
        <span>
          <span className="text-gray-400">Pace</span>{" "}
          {formatPace(preferences.pace)}
        </span>
        <span>
          <span className="text-gray-400">Walking</span>{" "}
          {formatWalkingTolerance(preferences.walking_tolerance)}
        </span>
        <span>
          <span className="text-gray-400">Mornings</span>{" "}
          {preferences.morning_preference ? "Yes" : "No"}
        </span>
      </div>
    </div>
  );
}
