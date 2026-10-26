/**
 * What a user reads when a v5 service cannot do what was asked (R6 Session Q).
 *
 * Every v5 client turns a failed response into one plain sentence here. A
 * service's own message is shown when it is written for people; anything that
 * reads like developer output (a port, a host, a file path, a stack trace, an
 * exception name, raw JSON, a bare status code) is replaced by a friendly
 * sentence, so nothing technical reaches a screen during a demo.
 */

export function unavailable(service: string): string {
  return `${service} is temporarily unavailable. Please try again in a moment.`;
}

const DEVELOPER_TEXT = new RegExp(
  [
    "traceback", "\\bfile \"", "\\.py\\b", "\\.sqlite", "\\.parquet", "\\.duckdb", "\\bops/", "v5\\.sh",
    "\\bport \\d{2,5}\\b", ":\\d{4,5}\\b", "127\\.0\\.0\\.1", "localhost", "/(home|users|private|tmp|var|opt)/",
    "\\bvar/", "internal server error", "\\w+(error|exception):", "operationalerror", "sqlite3",
    "\\bnull\\b", "\\bundefined\\b", "\\bnan\\b", "^\\s*[[{]", "^\\s*[45]\\d{2}(\\s+[a-z ]+)?\\.?$", "uvicorn",
    "\\berrno\\b", "econnrefused",
  ].join("|"),
  "i",
);

/** True when a message reads like developer output rather than a sentence for a user. */
export function isDeveloperText(message: string): boolean {
  return DEVELOPER_TEXT.test(message);
}

function byStatus(service: string, status: number): string {
  if (status === 0 || status === 502 || status === 503 || status === 504) return unavailable(service);
  if (status >= 500) return `${service} could not complete that just now. Please try again in a moment.`;
  if (status === 401) return "Your session has ended. Please sign in again.";
  if (status === 403) return "You do not have access to this.";
  if (status === 404) return "That item could not be found. It may have been moved or removed.";
  if (status === 409) return "Someone else changed this at the same time. Please reload and try again.";
  if (status === 413) return "That file is too large.";
  if (status === 422 || status === 400) return "Some of the details are not valid. Please check them and try again.";
  return `${service} could not complete that. Please try again.`;
}

/** The message carried by a FastAPI error body: `detail` as a string, `{message}`, or a validation list. */
export function detailMessage(body: unknown): string {
  if (!body || typeof body !== "object") return "";
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: unknown } | undefined;
    return typeof first?.msg === "string" ? first.msg : "";
  }
  if (detail && typeof detail === "object") {
    const m = (detail as { message?: unknown }).message;
    return typeof m === "string" ? m : "";
  }
  return "";
}

/** One plain sentence for a failed request to `service`. */
export function friendlyError(service: string, status: number, body: unknown): string {
  const said = detailMessage(body).trim();
  const isValidationList = Boolean(
    body && typeof body === "object" && Array.isArray((body as { detail?: unknown }).detail),
  );
  if (said && !isValidationList && !isDeveloperText(said)) return said;
  return byStatus(service, status);
}

/** A message that may come from anywhere (an Error, a string): developer text becomes a friendly sentence. */
export function friendlyMessage(e: unknown, service = "This service"): string {
  const m = e instanceof Error ? e.message : typeof e === "string" ? e : "";
  if (!m || isDeveloperText(m) || /^(failed to fetch|load failed|networkerror)/i.test(m)) return unavailable(service);
  return m;
}
