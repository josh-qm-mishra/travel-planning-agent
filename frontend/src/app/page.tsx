"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { TripRecord } from "@/lib/types";
import TripCard from "@/components/TripCard";

export default function HomePage() {
  const [trips, setTrips] = useState<TripRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.trips
      .list()
      .then(setTrips)
      .catch((err) => {
        setError(
          err instanceof ApiError
            ? err.message
            : "Failed to load trips. Is the backend running?",
        );
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Your Trips</h1>
          <p className="mt-1 text-sm text-gray-500">
            AI-planned itineraries, ready to explore
          </p>
        </div>
        <Link
          href="/trips/new"
          className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition-colors"
        >
          Plan a trip
        </Link>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-24 text-gray-400">
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
          Loading trips…
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {!loading && !error && trips.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="mb-4 rounded-full bg-blue-50 p-4">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="h-8 w-8 text-blue-400"
            >
              <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-gray-800">
            No trips yet
          </h2>
          <p className="mt-1 text-sm text-gray-500 max-w-xs">
            Plan your first trip and get a personalised AI-powered itinerary in
            seconds.
          </p>
          <Link
            href="/trips/new"
            className="mt-5 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            Plan your first trip
          </Link>
        </div>
      )}

      {!loading && !error && trips.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {trips.map((record) => (
            <TripCard key={record.id} record={record} />
          ))}
        </div>
      )}
    </div>
  );
}
