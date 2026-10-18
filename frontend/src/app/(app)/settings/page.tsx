"use client";

import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import {
  getDashboardAutoRefresh,
  setDashboardAutoRefresh,
} from "@/features/settings/preferences";
import { clearSession, getStoredUser } from "@/lib/auth";
import type { AuthUser } from "@/types/auth";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

/** Cache so getSnapshot returns a stable reference */
let cachedRaw: string | null = null;
let cachedUser: AuthUser | null = null;

function readUserCached(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem("ssp_user");
  if (raw === cachedRaw) return cachedUser;
  cachedRaw = raw;
  if (!raw) {
    cachedUser = null;
    return null;
  }
  try {
    cachedUser = JSON.parse(raw) as AuthUser;
  } catch {
    cachedUser = null;
  }
  return cachedUser;
}

function subscribe(onStoreChange: () => void) {
  const handler = () => {
    cachedRaw = null;
    cachedUser = null;
    onStoreChange();
  };
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}

function getUserSnapshot(): AuthUser | null {
  return readUserCached();
}

function getServerUserSnapshot(): AuthUser | null {
  return null;
}

function displayName(user: AuthUser | null): string {
  if (!user) return "Not signed in";
  const name = [user.firstName, user.lastName].filter(Boolean).join(" ").trim();
  return name || user.username || user.email || "User";
}

export default function SettingsPage() {
  const router = useRouter();
  const user = useSyncExternalStore(
    subscribe,
    getUserSnapshot,
    getServerUserSnapshot,
  );

  // Single useState only — lazy init from localStorage
  const [autoRefresh, setAutoRefreshState] = useState(() =>
    typeof window === "undefined" ? true : getDashboardAutoRefresh(),
  );

  function onToggleAutoRefresh() {
    const next = !autoRefresh;
    setDashboardAutoRefresh(next);
    setAutoRefreshState(next);
  }

  function onSignOut() {
    clearSession();
    cachedRaw = null;
    cachedUser = null;
    router.replace("/login");
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
          Account
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-zinc-50">Settings</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Profile from login session · preferences stored locally
        </p>
      </div>

      <section className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
        <h2 className="text-sm font-medium text-zinc-100">Account</h2>
        {!user ? (
          <p className="text-sm text-zinc-500">Not signed in.</p>
        ) : (
          <dl className="space-y-2 text-sm">
            <Row label="Name" value={displayName(user)} />
            <Row label="Email" value={user.email} />
            <Row label="Username" value={user.username} />
            <div>
              <dt className="text-xs text-zinc-500">Roles</dt>
              <dd className="mt-1 flex flex-wrap gap-1">
                {(user.roles ?? []).length === 0 ? (
                  <span className="text-zinc-600">None</span>
                ) : (
                  (user.roles ?? []).map((r) => (
                    <span
                      key={r}
                      className="rounded-full border border-zinc-700 px-2 py-0.5 text-[11px] text-zinc-300"
                    >
                      {r}
                    </span>
                  ))
                )}
              </dd>
            </div>
            {(user.permissions?.length ?? 0) > 0 && (
              <div>
                <dt className="text-xs text-zinc-500">Permissions</dt>
                <dd className="mt-1 flex max-h-28 flex-wrap gap-1 overflow-y-auto">
                  {user.permissions!.map((p) => (
                    <span
                      key={p}
                      className="rounded border border-zinc-800 bg-zinc-950 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500"
                    >
                      {p}
                    </span>
                  ))}
                </dd>
              </div>
            )}
          </dl>
        )}
      </section>

      <section className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
        <h2 className="text-sm font-medium text-zinc-100">Security</h2>
        <p className="text-sm text-zinc-400">
          MFA:{" "}
          <span
            className={
              user?.mfaEnabled ? "text-emerald-400" : "text-zinc-500"
            }
          >
            {user == null ? "—" : user.mfaEnabled ? "Enabled" : "Disabled"}
          </span>
        </p>
        <p className="text-xs text-zinc-600">
          No change-password API in this build. MFA challenge only during login
          via POST /api/v1/auth/mfa/verify.
        </p>
      </section>

      <section className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
        <h2 className="text-sm font-medium text-zinc-100">Preferences</h2>
        <label className="flex cursor-pointer items-center justify-between gap-3 text-sm text-zinc-300">
          <span>Dashboard auto-refresh (30s)</span>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={onToggleAutoRefresh}
            className="h-4 w-4 rounded border-zinc-600"
          />
        </label>
        <p className="text-xs text-zinc-600">
          Stored in localStorage on this device.
        </p>
      </section>

      <section className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
        <h2 className="text-sm font-medium text-zinc-100">System</h2>
        <div>
          <p className="text-xs text-zinc-500">API endpoint</p>
          <p className="mt-0.5 break-all font-mono text-xs text-zinc-300">
            {API_BASE}
          </p>
        </div>
        {user && (
          <button
            type="button"
            onClick={onSignOut}
            className="rounded-md border border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-300 hover:border-red-800 hover:text-red-300"
          >
            Sign out
          </button>
        )}
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-zinc-500">{label}</dt>
      <dd className="mt-0.5 text-zinc-200">{value || "—"}</dd>
    </div>
  );
}