"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { TripRecord, ReplanResponse } from "@/lib/types";
import { formatDateRange, formatCost } from "@/utils/format";
import DaySection from "@/components/DaySection";
import TripPreferencesSummary from "@/components/TripPreferencesSummary";
import ReplanPanel from "@/components/ReplanPanel";

export default function TripDetailPage() {
  const params = useParams();
  const tripId = params.tripId as string;

  const [record, setRecord] = useState<TripRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await api.trips.get(tripId);
        setRecord(data);
        setError(null);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.message : "Failed to load trip.",
        );
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [tripId]);

  function handleReplanned(response: ReplanResponse) {
    setRecord({ id: response.id, trip: response.trip, created_at: response.created_at, updated_at: response.updated_at });
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32 text-gray-400">
        <svg
          className="h-6 w-6 animate-spin mr-3"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        Loading itinerary…
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-10">
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
        >
          {error}
        </div>
        <Link
          href="/"
          className="mt-4 inline-block text-sm text-blue-600 hover:underline"
        >
          ← Back to trips
        </Link>
      </div>
    );
  }

  if (!record) return null;

  const { trip } = record;
  const totalCost = trip.days.reduce(
    (sum, d) => d.activities.reduce((s, a) => s + a.estimated_cost, 0) + sum,
    0,
  );

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Link
        href="/"
        className="mb-6 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 transition-colors"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="h-4 w-4"
        >
          <path
            fillRule="evenodd"
            d="M12.79 5.23a.75.75 0 01-.02 1.06L8.832 10l3.938 3.71a.75.75 0 11-1.04 1.08l-4.5-4.25a.75.75 0 010-1.08l4.5-4.25a.75.75 0 011.06.02z"
            clipRule="evenodd"
          />
        </svg>
        All trips
      </Link>

      {/* Hero */}
      <div className="mb-8 rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{trip.destination}</h1>
            <p className="mt-1 text-sm text-gray-500">
              {formatDateRange(trip.start_date, trip.end_date)} ·{" "}
              {trip.days.length} {trip.days.length === 1 ? "day" : "days"}
            </p>
          </div>
          <div className="text-right">
            {trip.total_budget != null && (
              <p className="text-xs text-gray-400 mb-0.5">Budget</p>
            )}
            {trip.total_budget != null && (
              <p className="text-lg font-semibold text-gray-900">
                {formatCost(trip.total_budget)}
              </p>
            )}
            {totalCost > 0 && (
              <p className="text-xs text-gray-400">
                Est. cost: {formatCost(totalCost)}
              </p>
            )}
          </div>
        </div>

        {/* Preferences summary */}
        <div className="mt-5 pt-5 border-t border-gray-100">
          <TripPreferencesSummary preferences={trip.preferences} />
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_320px] items-start">
        {/* Itinerary */}
        <div className="space-y-8">
          {trip.days.length === 0 ? (
            <p className="text-sm text-gray-400 italic text-center py-12">
              No itinerary yet.
            </p>
          ) : (
            trip.days.map((day) => (
              <DaySection key={day.date} day={day} />
            ))
          )}
        </div>

        {/* Sidebar */}
        <div className="lg:sticky lg:top-20">
          <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
            <ReplanPanel tripId={tripId} onReplanned={handleReplanned} />
          </div>
        </div>
      </div>
    </div>
  );
}
