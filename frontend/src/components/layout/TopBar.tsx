"use client";

export function TopBar() {
  const now = new Date().toISOString().slice(11, 19);

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-zinc-800 bg-zinc-900/90 px-4">
      <div>
        <h1 className="text-sm font-semibold tracking-wide text-zinc-100">
          Secure Surveillance Platform
        </h1>
      </div>
      <div className="flex items-center gap-4 text-xs text-zinc-400">
        <span className="font-mono">{now} UTC</span>
        <span className="rounded-full border border-zinc-700 px-2 py-0.5 text-zinc-300">
          User
        </span>
      </div>
    </header>
  );
}