"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { clearSession, getStoredUser } from "@/lib/auth";
import type { AuthUser } from "@/types/auth";

const USER_KEY = "ssp_user";

let cachedRaw: string | null | undefined = undefined;
let cachedUser: AuthUser | null = null;

function subscribe(onStoreChange: () => void) {
  // Optional: same-tab updates if you ever write user from another component
  window.addEventListener("storage", onStoreChange);
  return () => window.removeEventListener("storage", onStoreChange);
}

function getUserSnapshot(): AuthUser | null {
  const raw = sessionStorage.getItem(USER_KEY);
  if (raw === cachedRaw) {
    return cachedUser;
  }
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

function getServerUserSnapshot(): AuthUser | null {
  return null;
}

function displayName(user: AuthUser | null): string {
  if (!user) return "Not signed in";
  if (user.username) return user.username;
  if (user.email) return user.email;
  const full = `${user.firstName} ${user.lastName}`.trim();
  return full || "Not signed in";
}

export function TopBar() {
  const router = useRouter();
  const user = useSyncExternalStore(
    subscribe,
    getUserSnapshot,
    getServerUserSnapshot,
  );
  const [now, setNow] = useState<string | null>(null);
    
  function formatClock(d = new Date()) {
    return d.toLocaleTimeString("en-GB", {
      timeZone: "Africa/Gaborone",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }  

  useEffect(() => {
    //const format = () => new Date().toISOString().slice(11, 19);
    const id = window.setInterval(() => {
      setNow(formatClock());
    }, 1000);
    const raf = window.requestAnimationFrame(() => {
      setNow(formatClock());
    });
    return () => {
      window.clearInterval(id);
      window.cancelAnimationFrame(raf);
    };
  }, []);

  function onLogout() {
    clearSession();
    cachedRaw = null;
    cachedUser = null;
    router.replace("/login");
  }

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-zinc-800 bg-zinc-900/90 px-4">
      <h1 className="text-sm font-semibold tracking-wide text-zinc-100">
        Secure Surveillance Platform
      </h1>
      <div className="flex items-center gap-3 text-xs text-zinc-400">
        <span className="font-mono tabular-nums">{now ?? "--:--:--"} CAT</span>
        <span className="max-w-[10rem] truncate rounded-full border border-zinc-700 px-2 py-0.5 text-zinc-300">
          {displayName(user)}
        </span>
        {user ? (
          <button
            type="button"
            onClick={onLogout}
            className="rounded-md border border-zinc-700 px-2 py-1 text-zinc-300 hover:border-zinc-500 hover:text-zinc-100"
          >
            Sign out
          </button>
        ) : null}
      </div>
    </header>
  );
}