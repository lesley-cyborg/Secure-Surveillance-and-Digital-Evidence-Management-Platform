"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { setSession } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api";
import type {
  LoginSuccessResponse,
  MfaChallengeResponse,
} from "@/types/auth";

function isMfaChallenge(
  body: LoginSuccessResponse | MfaChallengeResponse,
): body is MfaChallengeResponse {
  return "mfaRequired" in body && body.mfaRequired === true;
}

export default function LoginPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier, password }),
      });

      const body = (await response.json()) as
        | LoginSuccessResponse
        | MfaChallengeResponse
        | { detail?: string | { message?: string; code?: string } };

      if (response.status === 202 && isMfaChallenge(body as MfaChallengeResponse)) {
        const mfa = body as MfaChallengeResponse;
        sessionStorage.setItem("ssp_mfa_challenge_id", mfa.challengeId);
        setError(mfa.message || "MFA verification is required");
        // Later: router.push("/login/mfa")
        return;
      }

      if (!response.ok) {
        const detail = (body as { detail?: unknown }).detail;
        let message = `Login failed (${response.status})`;
        if (typeof detail === "string") message = detail;
        else if (detail && typeof detail === "object" && "message" in detail) {
          message = String((detail as { message: string }).message);
        }
        setError(message);
        return;
      }

      const success = body as LoginSuccessResponse;
      if (!success.user || !success.tokens) {
        setError("Unexpected login response from server");
        return;
      }

      setSession(success.user, success.tokens);
      router.push("/dashboard");
    } catch {
      setError(
        "Could not reach the API. Is the backend running on the URL in .env.local?",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-900 p-8 shadow-xl">
      <div className="mb-8 text-center">
        <h1 className="text-lg font-semibold tracking-wide text-zinc-50">
          Secure Surveillance Platform
        </h1>
        <p className="mt-1 text-sm text-zinc-500">Sign in to continue</p>
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">
            Email or username
          </label>
          <input
            type="text"
            required
            autoComplete="username"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
            placeholder="admin@example.com"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">
            Password
          </label>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
            placeholder="••••••••••••"
          />
        </div>

        {error ? (
          <p className="text-sm text-red-400" role="alert">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={loading}
          className="mt-2 w-full rounded-md bg-zinc-100 py-2.5 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-60"
        >
          {loading ? "Signing in…" : "Sign In"}
        </button>
      </form>
    </div>
  );
}