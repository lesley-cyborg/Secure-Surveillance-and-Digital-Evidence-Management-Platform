"use client";

import { useCallback, useEffect, useState } from "react";
import { Camera as CameraIcon, Wifi, WifiOff, Activity, Loader2 } from "lucide-react";
import { listCameras, testCamera } from "@/features/cameras/api";
import type { Camera } from "@/types/camera";

function isOnline(c: Camera): boolean {
  const s = (c.status ?? "").toLowerCase();
  if (s === "online" || s === "active") return true;
  if (c.isActive === true && !s) return true;
  return false;
}

export default function CamerasPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null); // Track which camera is testing

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCameras(await listCameras());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load cameras");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleTest = async (cameraId: string) => {
    setTestingId(cameraId);
    try {
      const result = await testCamera(cameraId);
      if (result.reachable) {
        alert(`✅ Camera is reachable! Latency: ${result.latencyMs?.toFixed(0)}ms`);
      } else {
        alert(`⚠️ Unreachable: ${result.message}`);
      }
      // Refresh the list to reflect any status changes made by the backend probe
      await refresh();
    } catch (e) {
      alert(`Test failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setTestingId(null);
    }
  };

  const online = cameras.filter(isOnline).length;

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Monitoring
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-50">Cameras</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Registered devices and connectivity status
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          className="rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-50 transition"
        >
          Refresh
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">Total</p>
          <p className="mt-2 text-2xl font-semibold text-zinc-50">
            {cameras.length}
          </p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">Online</p>
          <p className="mt-2 text-2xl font-semibold text-emerald-400">{online}</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">
            Offline / other
          </p>
          <p className="mt-2 text-2xl font-semibold text-zinc-50">
            {cameras.length - online}
          </p>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-zinc-500">Loading cameras…</p>
      ) : error ? (
        <p className="text-sm text-red-400">{error}</p>
      ) : cameras.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-8 text-center">
          <CameraIcon className="mx-auto h-8 w-8 text-zinc-600" />
          <p className="mt-3 text-sm text-zinc-400">No cameras registered yet.</p>
          <p className="mt-1 text-xs text-zinc-600">
            Create cameras via API/Swagger, then refresh.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {cameras.map((c) => {
            const onlineCam = isOnline(c);
            const title = c.name ?? c.cameraCode ?? c.id.slice(0, 8);
            const isTesting = testingId === c.id;

            return (
              <div
                key={c.id}
                className="flex flex-col rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 transition hover:border-zinc-700"
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-100">
                      {title}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-zinc-500">
                      {c.ipAddress} {c.protocol ? `(${c.protocol})` : ""}
                    </p>
                  </div>
                  {onlineCam ? (
                    <Wifi className="h-4 w-4 shrink-0 text-emerald-400" />
                  ) : (
                    <WifiOff className="h-4 w-4 shrink-0 text-zinc-500" />
                  )}
                </div>

                {/* Status Row */}
                <div className="mt-3 flex items-center gap-2 text-xs">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      onlineCam ? "bg-emerald-400" : "bg-zinc-500"
                    }`}
                  />
                  <span className={onlineCam ? "text-emerald-400" : "text-zinc-500"}>
                    {c.status ? c.status.toUpperCase() : (onlineCam ? "ONLINE" : "OFFLINE")}
                  </span>
                  {c.lastSeenAt && (
                    <span className="ml-auto text-zinc-600">
                      {new Date(c.lastSeenAt).toLocaleTimeString()}
                    </span>
                  )}
                </div>

                {/* Test Button */}
                <div className="mt-4 pt-3 border-t border-zinc-800">
                  <button
                    type="button"
                    onClick={() => handleTest(c.id)}
                    disabled={isTesting}
                    className="flex w-full items-center justify-center gap-2 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs font-medium text-zinc-300 transition hover:bg-zinc-700 hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isTesting ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Testing...
                      </>
                    ) : (
                      <>
                        <Activity className="h-3.5 w-3.5" />
                        Test Connection
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}