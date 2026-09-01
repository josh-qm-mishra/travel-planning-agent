import Link from "next/link";
import type { TripRecord } from "@/lib/types";
import { formatDateRange, formatCost } from "@/utils/format";

export default function TripCard({ record }: { record: TripRecord }) {
  const { trip } = record;
  const dayCount =
    trip.days.length ||
    Math.round(
      (new Date(trip.end_date).getTime() - new Date(trip.start_date).getTime()) /
        86_400_000,
    ) + 1;
  const totalActivities = trip.days.reduce(
    (sum, d) => sum + d.activities.length,
    0,
  );

  return (
    <Link
      href={`/trips/${record.id}`}
      className="group block rounded-2xl border border-gray-100 bg-white p-5 shadow-sm transition hover:shadow-md hover:border-blue-200"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-bold text-gray-900 group-hover:text-blue-700 transition-colors truncate">
            {trip.destination}
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            {formatDateRange(trip.start_date, trip.end_date)}
          </p>
        </div>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="h-5 w-5 text-gray-300 group-hover:text-blue-400 transition-colors flex-shrink-0 mt-1"
        >
          <path
            fillRule="evenodd"
            d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
            clipRule="evenodd"
          />
        </svg>
      </div>

      <div className="mt-4 flex flex-wrap gap-4 text-sm text-gray-600">
        <span className="flex items-center gap-1">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4 text-gray-400"
          >
            <path
              fillRule="evenodd"
              d="M5.75 2a.75.75 0 01.75.75V4h7V2.75a.75.75 0 011.5 0V4h.25A2.75 2.75 0 0118 6.75v8.5A2.75 2.75 0 0115.25 18H4.75A2.75 2.75 0 012 15.25v-8.5A2.75 2.75 0 014.75 4H5V2.75A.75.75 0 015.75 2zm-1 5.5c-.69 0-1.25.56-1.25 1.25v6.5c0 .69.56 1.25 1.25 1.25h10.5c.69 0 1.25-.56 1.25-1.25v-6.5c0-.69-.56-1.25-1.25-1.25H4.75z"
              clipRule="evenodd"
            />
          </svg>
          {dayCount} {dayCount === 1 ? "day" : "days"}
        </span>
        <span className="flex items-center gap-1">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4 text-gray-400"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 000-1.5h-3.25V5z"
              clipRule="evenodd"
            />
          </svg>
          {totalActivities} activities
        </span>
        {trip.total_budget != null && (
          <span className="flex items-center gap-1">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="h-4 w-4 text-gray-400"
            >
              <path d="M10.75 10.818v2.614A3.13 3.13 0 0011.888 13c.482-.315.612-.648.612-.875 0-.227-.13-.56-.612-.875a3.13 3.13 0 00-1.138-.432zM8.33 8.62c.053.055.115.11.184.164.208.16.46.284.736.363V6.603a2.45 2.45 0 00-.35.13c-.14.065-.27.143-.386.233-.377.292-.514.627-.514.909 0 .184.058.39.33.615z" />
              <path
                fillRule="evenodd"
                d="M19 10.5a8.5 8.5 0 11-17 0 8.5 8.5 0 0117 0zM8.25 6.25a.75.75 0 01.75-.75h.008a.75.75 0 01.75.75v.334a3.636 3.636 0 011.27.463c.441.297.972.783.972 1.588 0 .722-.361 1.269-.757 1.611a4.57 4.57 0 01-1.485.723v2.069c.308-.09.575-.253.695-.43a.75.75 0 011.202.9c-.357.477-.947.81-1.897.957V14a.75.75 0 01-1.5 0v-.248c-.808-.079-1.473-.326-1.964-.739a3.231 3.231 0 01-1.097-2.426.75.75 0 011.5 0c0 .481.22.86.514 1.098.115.09.245.169.385.234V9.355c-.286-.07-.559-.183-.784-.344C6.43 8.696 6 8.137 6 7.338c0-.805.531-1.368.949-1.676a4.25 4.25 0 011.301-.59V4.75A.75.75 0 019 4a.75.75 0 01.75.75v.334a.75.75 0 01-.75.75h-.5V6.25z"
                clipRule="evenodd"
              />
            </svg>
            {formatCost(trip.total_budget)} budget
          </span>
        )}
      </div>

      {trip.preferences.interests.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {trip.preferences.interests.slice(0, 4).map((interest) => (
            <span
              key={interest}
              className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs text-blue-600"
            >
              {interest}
            </span>
          ))}
          {trip.preferences.interests.length > 4 && (
            <span className="rounded-full bg-gray-50 px-2.5 py-0.5 text-xs text-gray-500">
              +{trip.preferences.interests.length - 4} more
            </span>
          )}
        </div>
      )}
    </Link>
  );
}
