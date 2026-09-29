"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { setAccessToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    // M1: UI-only. M2: call backend login API.
    setAccessToken("m1-dev-placeholder-token");
    router.push("/dashboard");
  }

  return (
    <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-900 p-8 shadow-xl">
      <div className="mb-8 text-center">
        <h1 className="text-lg font-semibold tracking-wide text-zinc-50">
          Secure Surveillance and Digital Evidence Management Platform
        </h1>
        <p className="mt-1 text-sm text-zinc-500">Sign in to continue</p>
      </div>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">
            Email
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
            placeholder="you@example.com"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">
            Password
          </label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
            placeholder="••••••••••••••••"
          />
        </div>
        <button
          type="submit"
          className="mt-2 w-full rounded-md bg-zinc-100 py-2.5 text-sm font-medium text-zinc-900 hover:bg-white"
        >
          Sign In
        </button>
      </form>
      <p className="mt-6 text-center text-xs text-zinc-600">
        Milestone 1 — authentication UI only
      </p>
    </div>
  );
}