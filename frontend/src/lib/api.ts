import type {
  TripRecord,
  CreateTripResponse,
  ReplanResponse,
  TripPlanRequest,
} from "./types";
import { getClientId } from "./client-id";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const clientId = getClientId();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(clientId ? { "X-Client-ID": clientId } : {}),
      ...init.headers,
    },
    ...init,
  });

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body?.detail)) {
        message = body.detail.map((e: { msg?: string }) => e.msg).join("; ");
      } else if (typeof body?.message === "string") {
        message = body.message;
      }
    } catch {
      // keep default message
    }
    throw new ApiError(res.status, message);
  }

  return res.json() as Promise<T>;
}

export const api = {
  health(): Promise<{ status: string; service: string }> {
    return request("/health");
  },
  trips: {
    list(): Promise<TripRecord[]> {
      return request("/trips");
    },
    get(id: string): Promise<TripRecord> {
      return request(`/trips/${id}`);
    },
    create(data: TripPlanRequest): Promise<CreateTripResponse> {
      return request("/trips", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    replan(
      id: string,
      change_request: string,
      expected_version?: number,
    ): Promise<ReplanResponse> {
      return request(`/trips/${id}/replan`, {
        method: "POST",
        body: JSON.stringify({ change_request, expected_version }),
      });
    },
  },
};
