export function formatTime(hhmm: string): string {
  const [hourStr, minStr] = hhmm.split(":");
  const hour = parseInt(hourStr, 10);
  const min = minStr ?? "00";
  const period = hour >= 12 ? "PM" : "AM";
  const h = hour % 12 || 12;
  return `${h}:${min} ${period}`;
}

export function formatDate(ymd: string): string {
  // Parse as local date to avoid timezone shifts
  const [year, month, day] = ymd.split("-").map(Number);
  const d = new Date(year, month - 1, day);
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "long",
    day: "numeric",
  });
}

export function formatDateRange(start: string, end: string): string {
  const [sy, sm, sd] = start.split("-").map(Number);
  const [ey, em, ed] = end.split("-").map(Number);
  const s = new Date(sy, sm - 1, sd);
  const e = new Date(ey, em - 1, ed);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString("en-US", opts)} – ${e.toLocaleDateString("en-US", { ...opts, year: "numeric" })}`;
}

export function formatCost(n: number): string {
  if (n === 0) return "Free";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

export function formatCategory(cat: string): string {
  const map: Record<string, string> = {
    food_and_drink: "Food & Drink",
    food: "Food & Drink",
    attraction: "Attraction",
    transport: "Transport",
    accommodation: "Accommodation",
    hotel: "Hotel",
    shopping: "Shopping",
    outdoor: "Outdoor",
    entertainment: "Entertainment",
    culture: "Culture",
    wellness: "Wellness",
    nightlife: "Nightlife",
    museum: "Museum",
    restaurant: "Restaurant",
    cafe: "Café",
    bar: "Bar",
    sightseeing: "Sightseeing",
    landmark: "Landmark",
    park: "Park",
    tour: "Tour",
    meal: "Meal",
    "amusement center": "Amusement",
    activity: "Activity",
  };
  return (
    map[cat.toLowerCase()] ??
    cat.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

export function formatPace(p: string): string {
  const map: Record<string, string> = {
    relaxed: "Relaxed",
    moderate: "Moderate",
    busy: "Busy",
  };
  return map[p] ?? p;
}

export function formatWalkingTolerance(w: string): string {
  const map: Record<string, string> = {
    low: "Low",
    moderate: "Moderate",
    high: "High",
  };
  return map[w] ?? w;
}
