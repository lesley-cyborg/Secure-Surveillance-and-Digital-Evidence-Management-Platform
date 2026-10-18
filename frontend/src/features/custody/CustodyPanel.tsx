"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  acceptEvidenceTransfer,
  initiateEvidenceTransfer,
  listCustodyEvents,
  rejectEvidenceTransfer,
} from "@/features/custody/api";
import { listUsers } from "@/features/users/api";
import {
  canAcceptCustodyTransfer,
  canInitiateCustodyTransfer,
  canRejectCustodyTransfer,
  currentUserId,
} from "@/lib/permissions";
import type { CustodyEvent, EvidenceTransfer } from "@/types/custody";

type UserOption = { id: string; email: string; username?: string };

type Props = {
  evidenceId: string;
};

export function CustodyPanel({ evidenceId }: Props) {
  const me = currentUserId();
  const [transfer, setTransfer] = useState<EvidenceTransfer | null>(null);
  const [events, setEvents] = useState<CustodyEvent[]>([]);
  const [users, setUsers] = useState<UserOption[]>([]);
  const [toUserId, setToUserId] = useState("");
  const [purpose, setPurpose] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionOk, setActionOk] = useState<string | null>(null);

  const canStart = canInitiateCustodyTransfer();
  const canAccept =
    canAcceptCustodyTransfer() &&
    transfer?.status === "PENDING" &&
    me != null &&
    transfer.toUserId === me;
  const canReject =
    canRejectCustodyTransfer() &&
    transfer?.status === "PENDING" &&
    me != null &&
    transfer.toUserId === me;


    const refreshEvents = useCallback(async () => {
    setLoadingEvents(true);
    setEventsError(null);
    try {
        const data = await listCustodyEvents(evidenceId, 1, 25);
        setEvents(data.items ?? []);
    } catch (e) {
        setEvents([]);
        setEventsError(
        e instanceof Error ? e.message : "Could not load custody history",
        );
    } finally {
        setLoadingEvents(false);
    }
    }, [evidenceId]);

  useEffect(() => {
    void refreshEvents();
  }, [refreshEvents]);

  useEffect(() => {
    if (!canStart) return;
    void (async () => {
      try {
        const list = await listUsers();
        const rows = Array.isArray(list)
          ? list
          : ((list as { items?: UserOption[] }).items ?? []);
        setUsers(rows);
        if (rows[0]?.id) setToUserId(rows[0].id);
      } catch {
        /* UUID fallback */
      }
    })();
  }, [canStart]);

  async function onInitiate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const t = await initiateEvidenceTransfer(evidenceId, {
        toUserId,
        purpose: purpose.trim(),
      });
      setTransfer(t);
      setPurpose("");
      await refreshEvents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Transfer failed");
    } finally {
      setBusy(false);
    }
  }

  async function onAccept() {
    if (!transfer) return;
    setError(null);
    setBusy(true);
    try {
      const t = await acceptEvidenceTransfer(evidenceId, transfer.id, {
        comment: comment.trim() || null,
      });
      setTransfer(t);
      setComment("");
      await refreshEvents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Accept failed");
    } finally {
      setBusy(false);
    }
  }

  async function onReject() {
    if (!transfer) return;
    setError(null);
    setBusy(true);
    try {
      const t = await rejectEvidenceTransfer(evidenceId, transfer.id, {
        comment: comment.trim() || null,
      });
      setTransfer(t);
      setComment("");
      await refreshEvents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 space-y-4">
      <div>
        <h2 className="text-xs font-medium uppercase tracking-wide text-zinc-500">
          Chain of custody
        </h2>
        <p className="mt-1 text-xs text-zinc-600">
          Transfers require recipient accept/reject. Events are hashed and signed.
        </p>
      </div>

      {/* Timeline */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-zinc-400">History</p>
        {loadingEvents ? (
          <p className="text-xs text-zinc-600">Loading events…</p>
        ) : events.length === 0 ? (
          <p className="text-xs text-zinc-600">No custody events yet.</p>
        ) : (
          <ul className="space-y-2 max-h-64 overflow-y-auto">
            {events.map((ev) => (
              <li
                key={ev.id}
                className="rounded-md border border-zinc-800 bg-zinc-950/40 px-3 py-2 text-xs"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-zinc-200">{ev.eventType}</span>
                  <span className="text-zinc-600">
                    {new Date(ev.occurredAt).toLocaleString()}
                  </span>
                </div>
                {ev.purpose && (
                  <p className="mt-1 text-zinc-500">{ev.purpose}</p>
                )}
                {ev.recordHash && (
                  <p className="mt-1 font-mono text-[10px] text-zinc-600 truncate">
                    {ev.recordHash}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {transfer && (
        <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3 text-sm space-y-1">
          <p className="text-zinc-200">
            Last transfer:{" "}
            <span
              className={
                transfer.status === "PENDING"
                  ? "text-amber-400"
                  : transfer.status === "ACCEPTED"
                    ? "text-emerald-400"
                    : "text-zinc-400"
              }
            >
              {transfer.status}
            </span>
          </p>
          <p className="text-xs text-zinc-500 font-mono break-all">{transfer.id}</p>
          <p className="text-xs text-zinc-400">{transfer.purpose}</p>
        </div>
      )}

      {canStart && (
        <form onSubmit={onInitiate} className="space-y-3 border-t border-zinc-800 pt-4">
          <p className="text-xs font-medium text-zinc-400">Initiate transfer</p>
          {users.length > 0 ? (
            <select
              value={toUserId}
              onChange={(e) => setToUserId(e.target.value)}
              className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
              required
            >
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.email}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={toUserId}
              onChange={(e) => setToUserId(e.target.value)}
              placeholder="Recipient user UUID"
              required
              className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm font-mono text-zinc-100"
            />
          )}
          <input
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            required
            minLength={3}
            placeholder="Purpose"
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs font-medium text-zinc-200 disabled:opacity-50"
          >
            {busy ? "Submitting…" : "Initiate transfer"}
          </button>
        </form>
      )}

      {(canAccept || canReject) && (
        <div className="space-y-3 border-t border-zinc-800 pt-4">
          <p className="text-xs font-medium text-zinc-400">Your decision</p>
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Optional comment"
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
          />
          <div className="flex gap-2">
            {canAccept && (
              <button
                type="button"
                onClick={() => void onAccept()}
                disabled={busy}
                className="rounded-md border border-emerald-900/50 bg-emerald-950/40 px-3 py-2 text-xs text-emerald-300 disabled:opacity-50"
              >
                Accept
              </button>
            )}
            {canReject && (
              <button
                type="button"
                onClick={() => void onReject()}
                disabled={busy}
                className="rounded-md border border-red-900/50 bg-red-950/40 px-3 py-2 text-xs text-red-300 disabled:opacity-50"
              >
                Reject
              </button>
            )}
          </div>
        </div>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}
    </section>
  );
}