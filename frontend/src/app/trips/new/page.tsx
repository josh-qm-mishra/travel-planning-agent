"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { TripPlanRequest, Pace, WalkingTolerance } from "@/lib/types";
import TagInput from "@/components/TagInput";

function Label({
  htmlFor,
  children,
}: {
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className="block text-sm font-medium text-gray-700 mb-1"
    >
      {children}
    </label>
  );
}

function FieldGroup({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      {htmlFor ? (
        <Label htmlFor={htmlFor}>{label}</Label>
      ) : (
        <span className="block text-sm font-medium text-gray-700 mb-1">
          {label}
        </span>
      )}
      {children}
    </div>
  );
}

function TextInput({
  id,
  value,
  onChange,
  placeholder,
  type = "text",
  required,
  min,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  required?: boolean;
  min?: string;
}) {
  return (
    <input
      id={id}
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      required={required}
      min={min}
      className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none transition"
    />
  );
}

function RadioGroup<T extends string>({
  name,
  options,
  value,
  onChange,
}: {
  name: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex gap-3 flex-wrap">
      {options.map((opt) => (
        <label
          key={opt.value}
          className={`flex items-center gap-2 cursor-pointer rounded-lg border px-3 py-2 text-sm transition ${
            value === opt.value
              ? "border-blue-500 bg-blue-50 text-blue-700 font-medium"
              : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
          }`}
        >
          <input
            type="radio"
            name={name}
            value={opt.value}
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
            className="sr-only"
          />
          {opt.label}
        </label>
      ))}
    </div>
  );
}

export default function NewTripPage() {
  const router = useRouter();

  const [destination, setDestination] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [budget, setBudget] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [foodPreferences, setFoodPreferences] = useState<string[]>([]);
  const [pace, setPace] = useState<Pace>("moderate");
  const [morningPref, setMorningPref] = useState(true);
  const [walkingTolerance, setWalkingTolerance] =
    useState<WalkingTolerance>("moderate");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const payload: TripPlanRequest = {
      destination: destination.trim(),
      start_date: startDate,
      end_date: endDate,
      interests,
      food_preferences: foodPreferences,
      pace,
      morning_preference: morningPref,
      walking_tolerance: walkingTolerance,
    };
    if (budget) payload.total_budget = Number(budget);

    try {
      const result = await api.trips.create(payload);
      router.push(`/trips/${result.id}`);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Something went wrong. Please try again.",
      );
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Plan a new trip</h1>
        <p className="mt-1 text-sm text-gray-500">
          Tell us about your trip and we&apos;ll build a personalised itinerary.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm space-y-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
            Destination & Dates
          </h2>

          <FieldGroup label="Destination" htmlFor="destination">
            <TextInput
              id="destination"
              value={destination}
              onChange={setDestination}
              placeholder="e.g. Tokyo, Japan"
              required
            />
          </FieldGroup>

          <div className="grid grid-cols-2 gap-4">
            <FieldGroup label="Start date" htmlFor="startDate">
              <TextInput
                id="startDate"
                type="date"
                value={startDate}
                onChange={setStartDate}
                required
              />
            </FieldGroup>
            <FieldGroup label="End date" htmlFor="endDate">
              <TextInput
                id="endDate"
                type="date"
                value={endDate}
                onChange={setEndDate}
                min={startDate}
                required
              />
            </FieldGroup>
          </div>

          <FieldGroup label="Total budget (USD, optional)" htmlFor="budget">
            <TextInput
              id="budget"
              type="number"
              value={budget}
              onChange={setBudget}
              placeholder="e.g. 1500"
              min="0"
            />
          </FieldGroup>
        </div>

        <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm space-y-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
            Interests & Food
          </h2>

          <FieldGroup label="Interests" htmlFor="interests">
            <TagInput
              id="interests"
              tags={interests}
              onChange={setInterests}
              placeholder="e.g. museums, hiking, art…"
            />
            <p className="mt-1 text-xs text-gray-400">
              Press Enter or comma to add each interest
            </p>
          </FieldGroup>

          <FieldGroup label="Food preferences" htmlFor="food">
            <TagInput
              id="food"
              tags={foodPreferences}
              onChange={setFoodPreferences}
              placeholder="e.g. vegetarian, sushi, street food…"
            />
            <p className="mt-1 text-xs text-gray-400">
              Press Enter or comma to add each preference
            </p>
          </FieldGroup>
        </div>

        <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm space-y-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
            Travel Style
          </h2>

          <FieldGroup label="Pace">
            <RadioGroup
              name="pace"
              value={pace}
              onChange={setPace}
              options={[
                { value: "relaxed", label: "Relaxed" },
                { value: "moderate", label: "Moderate" },
                { value: "busy", label: "Busy" },
              ]}
            />
          </FieldGroup>

          <FieldGroup label="Walking tolerance">
            <RadioGroup
              name="walking"
              value={walkingTolerance}
              onChange={setWalkingTolerance}
              options={[
                { value: "low", label: "Low" },
                { value: "moderate", label: "Moderate" },
                { value: "high", label: "High" },
              ]}
            />
          </FieldGroup>

          <FieldGroup label="Morning person?">
            <RadioGroup
              name="morning"
              value={morningPref ? "yes" : "no"}
              onChange={(v) => setMorningPref(v === "yes")}
              options={[
                { value: "yes", label: "Yes, start early" },
                { value: "no", label: "No, slow mornings" },
              ]}
            />
          </FieldGroup>
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <svg
                className="h-4 w-4 animate-spin"
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
              Planning your trip…
            </>
          ) : (
            "Plan my trip"
          )}
        </button>
      </form>
    </div>
  );
}
