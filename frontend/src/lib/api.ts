const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** An error response from the API, with Django REST Framework's error body. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(`API request failed with status ${status}`);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit & { token?: string } = {}): Promise<T> {
  const { token, headers, ...rest } = init;
  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    cache: "no-store",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      // JSON bodies are strings. For FormData (file uploads) the browser sets
      // the multipart Content-Type itself.
      ...(typeof rest.body === "string" ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
  });

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw new ApiError(response.status, body);
  }
  return (await response.json()) as T;
}

export type HealthResponse = {
  status: string;
};

export type Me = {
  id: number;
  clerk_id: string;
  role: "client" | "admin";
};

export const PROJECT_TYPES = {
  website: "Website",
  app: "App",
  dashboard: "Dashboard",
  other: "Other",
} as const;

export type ProjectType = keyof typeof PROJECT_TYPES;

export const PROJECT_STATUSES = {
  interviewing: "Interviewing",
  awaiting_client: "Awaiting client",
  awaiting_admin: "Awaiting admin",
  sent_to_github: "Sent to GitHub",
} as const;

export type ProjectStatus = keyof typeof PROJECT_STATUSES;

export type Project = {
  id: number;
  name: string;
  project_type: ProjectType;
  status: ProjectStatus;
  consent_given_at: string;
  consent_version: string;
  created_at: string;
};

export type Transcript = {
  id: number;
  text: string;
  /** The same text with personal data replaced by tags; what the AI sees. */
  masked_text: string;
  provider: string;
  duration_seconds: number | null;
  created_at: string;
};

export const QUESTION_TOPICS = {
  users: "Who will use it",
  roles: "Kinds of users",
  features: "What it must do",
  data: "Information it keeps",
  payments: "Payments",
  login: "Signing in",
  deadlines: "Dates and deadlines",
} as const;

/** A question the AI asks to fill a gap in the client's explanation. */
export type FollowUpQuestion = {
  id: number;
  topic: keyof typeof QUESTION_TOPICS;
  question: string;
  status: "open" | "answered" | "not_sure";
  answer: string;
  /** The answer with personal data replaced by tags; what the AI sees. */
  masked_answer: string;
  answered_at: string | null;
};

export const STORY_PRIORITIES = {
  must: "Must have",
  should: "Should have",
  nice: "Nice to have",
} as const;

export type StoryPriority = keyof typeof STORY_PRIORITIES;

/** "As a [role], I want to [goal], so that [reason]." */
export type UserStory = {
  id: number;
  role: string;
  goal: string;
  reason: string;
  acceptance_criteria: string[];
  priority: StoryPriority;
  provider: string;
  created_at: string;
};

export type NewProject = {
  name: string;
  project_type: ProjectType;
  consent: boolean;
};

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health/", { signal });
}

export function getMe(token: string, signal?: AbortSignal): Promise<Me> {
  return request<Me>("/api/me/", { token, signal });
}

export function listProjects(token: string, signal?: AbortSignal): Promise<Project[]> {
  return request<Project[]>("/api/projects/", { token, signal });
}

export function getProject(token: string, id: string, signal?: AbortSignal): Promise<Project> {
  return request<Project>(`/api/projects/${encodeURIComponent(id)}/`, { token, signal });
}

export function createProject(token: string, project: NewProject): Promise<Project> {
  return request<Project>("/api/projects/", {
    token,
    method: "POST",
    body: JSON.stringify(project),
  });
}

export function listTranscripts(
  token: string,
  projectId: number,
  signal?: AbortSignal,
): Promise<Transcript[]> {
  return request<Transcript[]>(`/api/projects/${projectId}/transcripts/`, { token, signal });
}

export function uploadRecording(token: string, projectId: number, audio: Blob): Promise<Transcript> {
  const extension = audio.type.includes("mp4") ? "mp4" : audio.type.includes("ogg") ? "ogg" : "webm";
  const form = new FormData();
  form.append("audio", audio, `recording.${extension}`);
  return request<Transcript>(`/api/projects/${projectId}/transcripts/`, {
    token,
    method: "POST",
    body: form,
  });
}

export function listStories(token: string, projectId: number, signal?: AbortSignal): Promise<UserStory[]> {
  return request<UserStory[]>(`/api/projects/${projectId}/stories/`, { token, signal });
}

export function writeStories(token: string, projectId: number): Promise<UserStory[]> {
  return request<UserStory[]>(`/api/projects/${projectId}/stories/`, { token, method: "POST" });
}

export function listQuestions(
  token: string,
  projectId: number,
  signal?: AbortSignal,
): Promise<FollowUpQuestion[]> {
  return request<FollowUpQuestion[]>(`/api/projects/${projectId}/questions/`, { token, signal });
}

export function askQuestions(token: string, projectId: number): Promise<FollowUpQuestion[]> {
  return request<FollowUpQuestion[]>(`/api/projects/${projectId}/questions/`, { token, method: "POST" });
}

/** Answer by text, or pass `null` for "Not sure". */
export function answerQuestion(
  token: string,
  projectId: number,
  questionId: number,
  answer: string | null,
): Promise<FollowUpQuestion> {
  return request<FollowUpQuestion>(`/api/projects/${projectId}/questions/${questionId}/answer/`, {
    token,
    method: "POST",
    body: JSON.stringify(answer === null ? { not_sure: true } : { answer }),
  });
}

export function answerQuestionByVoice(
  token: string,
  projectId: number,
  questionId: number,
  audio: Blob,
): Promise<FollowUpQuestion> {
  const extension = audio.type.includes("mp4") ? "mp4" : audio.type.includes("ogg") ? "ogg" : "webm";
  const form = new FormData();
  form.append("audio", audio, `answer.${extension}`);
  return request<FollowUpQuestion>(`/api/projects/${projectId}/questions/${questionId}/answer/`, {
    token,
    method: "POST",
    body: form,
  });
}