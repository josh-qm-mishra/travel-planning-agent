// TypeScript types mirroring the FastAPI backend response contracts.
// Times arrive as "HH:MM:SS" strings; dates as "YYYY-MM-DD".

export type Pace = "relaxed" | "moderate" | "busy";
export type WalkingTolerance = "low" | "moderate" | "high";

export interface TripPreferences {
  interests: string[];
  food_preferences: string[];
  pace: Pace;
  morning_preference: boolean;
  walking_tolerance: WalkingTolerance;
}

export interface TripConstraints {
  earliest_start_time: string | null;
  latest_end_time: string | null;
  maximum_budget: number | null;
}

export interface Activity {
  name: string;
  location: string;
  start_time: string; // "HH:MM:SS"
  end_time: string;
  estimated_cost: number;
  category: string;
  locked: boolean;
  notes: string | null;
}

export interface TripDay {
  date: string; // "YYYY-MM-DD"
  activities: Activity[];
}

export interface Trip {
  destination: string;
  start_date: string;
  end_date: string;
  total_budget: number | null;
  preferences: TripPreferences;
  constraints: TripConstraints;
  days: TripDay[];
}

export interface TripRecord {
  id: string;
  trip: Trip;
  created_at: string;
  updated_at: string;
}

export interface AgentRunMetadata {
  tools_called: string[];
  tool_call_count: number;
  validation_attempts: number;
  validation_failures: string[];
  success: boolean;
  error: string | null;
}

export interface CreateTripResponse extends TripRecord {
  agent_run: AgentRunMetadata;
}

export interface TripChangeSummary {
  activities_added: number;
  activities_removed: number;
  activities_changed: number;
  affected_dates: string[];
  budget_difference: number | null;
  locked_activities_changed: number;
  summary: string;
}

export interface ReplanResponse extends TripRecord {
  change_summary: TripChangeSummary;
}

export interface TripPlanRequest {
  destination: string;
  start_date: string;
  end_date: string;
  total_budget?: number;
  interests: string[];
  food_preferences: string[];
  pace: Pace;
  morning_preference: boolean;
  walking_tolerance: WalkingTolerance;
}

export interface ApiError {
  status: number;
  message: string;
}
