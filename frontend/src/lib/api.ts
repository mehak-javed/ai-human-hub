const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type HealthResponse = {
  status: string;
};

export type Me = {
  id: number;
  clerk_id: string;
  role: "client" | "admin";
};

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/api/health/`, {
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }

  return (await response.json()) as HealthResponse;
}

export async function getMe(token: string, signal?: AbortSignal): Promise<Me> {
  const response = await fetch(`${API_URL}/api/me/`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Request to /api/me/ failed with status ${response.status}`);
  }

  return (await response.json()) as Me;
}