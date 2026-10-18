/** Parse FastAPI-style errors into a short user message */
export async function readApiError(res: Response): Promise<string> {
  const fallback = `Request failed (${res.status})`;
  try {
    const data = (await res.json()) as {
      detail?:
        | string
        | { code?: string; message?: string }
        | Array { msg?: string; message?: string };
    };

    const d = data.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d.map((x) => x.msg || x.message || "Validation error").join("; ");
    }
    if (d && typeof d === "object") {
      if (d.message && d.code) return `${d.code}: ${d.message}`;
      if (d.message) return d.message;
      if (d.code) return d.code;
    }
  } catch {
    /* ignore non-JSON */
  }
  if (res.status === 401) return "Session expired — sign in again";
  if (res.status === 403) return "You do not have permission for this action";
  if (res.status === 404) return "Evidence or custody record was not found";
  if (res.status === 409) return "Custody conflict — refresh and try again";
  return fallback;
}