"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  Camera as CameraIcon,
  Wifi,
  WifiOff,
  Activity,
  Loader2,
  Plus,
  RefreshCw,
} from "lucide-react";
import { listCameras, createCamera, testCamera } from "@/features/cameras/api";
import { canCreateCameras, canTestCameras } from "@/lib/permissions";
import type { Camera, CameraCreateInput } from "@/types/camera";
import { LiveViewPanel } from "@/components/cameras/LiveViewPanel";

function statusTone(c: Camera): "online" | "offline" | "degraded" {
  const s = (c.status ?? "").toUpperCase();
  if (s === "ONLINE" || s === "ACTIVE") return "online";
  if (s === "DEGRADED") return "degraded";
  return "offline";
}

const emptyForm: CameraCreateInput = {
  siteId: "",
  name: "",
  cameraCode: "",
  ipAddress: "",
  protocol: "RTSP",
  streamUrl: "",
  credentialsSecretRef: "local://cameras/",
  locationDescription: "",
  status: "OFFLINE",
  isActive: true,
};

export default function CamerasPage() {
  const [canCreate, setCanCreate] = useState(false);
  const [canTest, setCanTest] = useState(false);

  useEffect(() => {
    setCanCreate(canCreateCameras());
    setCanTest(canTestCameras());
  }, []);

  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [liveCamera, setLiveCamera] = useState<Camera | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CameraCreateInput>(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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

  function updateField<K extends keyof CameraCreateInput>(
    key: K,
    value: CameraCreateInput[K],
  ) {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "cameraCode" && typeof value === "string") {
        next.credentialsSecretRef = `local://cameras/${value || "NEW"}/rtsp`;
      }
      return next;
    });
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    setSaving(true);
    try {
      const created = await createCamera({
        ...form,
        name: form.name.trim(),
        cameraCode: form.cameraCode.trim(),
        streamUrl: form.streamUrl.trim(),
        siteId: form.siteId.trim(),
        ipAddress: form.ipAddress.trim(),
        credentialsSecretRef: form.credentialsSecretRef.trim(),
        locationDescription: form.locationDescription?.trim() || null,
        protocol: form.protocol,
      });
      setFormSuccess(`Registered ${created.cameraCode} (${created.id})`);
      setForm(emptyForm);
      setShowForm(false);
      await refresh();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleTest(cameraId: string) {
    setTestingId(cameraId);
    try {
      const result = await testCamera(cameraId);
      const ok = result.reachable === true;
      alert(
        ok
          ? `Reachable: ${result.detail ?? result.message ?? "ok"}`
          : `Not reachable: ${result.detail ?? result.message ?? JSON.stringify(result)}`,
      );
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Test failed");
    } finally {
      setTestingId(null);
    }
  }

  const onlineCount = cameras.filter((c) => statusTone(c) === "online").length;

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-50">Cameras</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Directory and registration — stream URLs stay server-side
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void refresh()}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
          {canCreate && (
            <button
              type="button"
              onClick={() => {
                setShowForm((v) => !v);
                setFormError(null);
                setFormSuccess(null);
              }}
              className="inline-flex items-center gap-1.5 rounded-md bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-white"
            >
              <Plus className="h-3.5 w-3.5" />
              Register Camera
            </button>
          )}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Kpi label="Total" value={String(cameras.length)} />
        <Kpi label="Online" value={String(onlineCount)} />
        <Kpi
          label="Offline / other"
          value={String(cameras.length - onlineCount)}
        />
      </div>

      {formSuccess && (
        <p className="rounded-md border border-emerald-900/50 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-300">
          {formSuccess}
        </p>
      )}

      {canCreate && showForm && (
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">Register camera</h2>
          <p className="mt-0.5 mb-4 text-xs text-zinc-500">
            Same fields as POST /api/v1/cameras. RTSP URL is encrypted on the
            server; it is never shown back in the list.
          </p>

          <form onSubmit={onCreate} className="grid gap-3 sm:grid-cols-2">
            <Field
              label="Site ID (UUID)"
              required
              value={form.siteId}
              onChange={(v) => updateField("siteId", v)}
              placeholder="e.g. 27f37ce7-57a4-4885-aa35-8e704ba7e824"
            />
            <Field
              label="Name"
              required
              value={form.name}
              onChange={(v) => updateField("name", v)}
              placeholder="V380 Lab Camera"
            />
            <Field
              label="Camera code"
              required
              value={form.cameraCode}
              onChange={(v) => updateField("cameraCode", v)}
              placeholder="CAM-V380-01"
            />
            <Field
              label="IP address"
              required
              value={form.ipAddress}
              onChange={(v) => updateField("ipAddress", v)}
              placeholder="192.168.137.169"
            />
            <div className="sm:col-span-2">
              <Field
                label="Stream URL (RTSP)"
                required
                value={form.streamUrl}
                onChange={(v) => updateField("streamUrl", v)}
                placeholder="rtsp://192.168.137.169:554/live/ch00_1"
              />
            </div>
            <Field
              label="Credentials secret ref"
              required
              value={form.credentialsSecretRef}
              onChange={(v) => updateField("credentialsSecretRef", v)}
              placeholder="local://cameras/CAM-V380-01/rtsp"
            />
            <Field
              label="Location description"
              value={form.locationDescription ?? ""}
              onChange={(v) => updateField("locationDescription", v)}
              placeholder="Lab / hotspot"
            />

            <div>
              <label className="mb-1 block text-xs text-zinc-400">
                Protocol
              </label>
              <select
                value={form.protocol}
                onChange={(e) =>
                  updateField(
                    "protocol",
                    e.target.value as CameraCreateInput["protocol"],
                  )
                }
                className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
              >
                <option value="RTSP">RTSP</option>
                <option value="ONVIF">ONVIF</option>
                <option value="HTTPS">HTTPS</option>
              </select>
            </div>

            <div className="flex items-end gap-4 pb-1">
              <label className="flex items-center gap-2 text-xs text-zinc-400">
                <input
                  type="checkbox"
                  checked={form.isActive !== false}
                  onChange={(e) => updateField("isActive", e.target.checked)}
                  className="rounded border-zinc-600"
                />
                Active
              </label>
            </div>

            {formError && (
              <p className="sm:col-span-2 text-sm text-red-400">{formError}</p>
            )}

            <div className="sm:col-span-2 flex gap-2">
              <button
                type="submit"
                disabled={saving}
                className="rounded-md bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 disabled:opacity-60"
              >
                {saving ? "Registering…" : "Register"}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded-md border border-zinc-700 px-4 py-2 text-sm text-zinc-300"
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}

      {loading ? (
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : cameras.length === 0 ? (
        <p className="text-sm text-zinc-500">No cameras registered yet.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {cameras.map((c) => {
            const tone = statusTone(c);
            const isTesting = testingId === c.id;
            const canWatch = tone === "online";

            return (
              <div
                key={c.id}
                role={canWatch ? "button" : undefined}
                tabIndex={canWatch ? 0 : undefined}
                onClick={() => {
                  if (!canWatch) return;
                  setLiveCamera(c);
                }}
                onKeyDown={(e) => {
                  if (!canWatch) return;
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setLiveCamera(c);
                  }
                }}
                className={`rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 ${
                  canWatch
                    ? "cursor-pointer hover:border-zinc-600"
                    : "cursor-default"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <CameraIcon className="h-4 w-4 text-zinc-400" />
                    <div>
                      <p className="text-sm font-medium text-zinc-100">
                        {c.name}
                      </p>
                      <p className="font-mono text-xs text-zinc-500">
                        {c.cameraCode}
                      </p>
                    </div>
                  </div>
                  {tone === "online" ? (
                    <Wifi className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <WifiOff className="h-4 w-4 text-zinc-500" />
                  )}
                </div>

                <p className="mt-2 text-xs text-zinc-500">
                  {c.ipAddress} · {c.protocol}
                </p>
                {c.locationDescription ? (
                  <p className="text-xs text-zinc-600">{c.locationDescription}</p>
                ) : null}

                <div className="mt-3 flex items-center gap-2 text-xs">
                  <span
                    className={
                      tone === "online"
                        ? "text-emerald-400"
                        : tone === "degraded"
                          ? "text-amber-400"
                          : "text-zinc-500"
                    }
                  >
                    {(c.status ?? "OFFLINE").toUpperCase()}
                  </span>
                  {c.lastSeenAt ? (
                    <span className="ml-auto text-zinc-600">
                      {new Date(c.lastSeenAt).toLocaleTimeString("en-GB", {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                        hour12: false,
                      })}
                    </span>
                  ) : null}
                </div>

                {canWatch ? (
                  <p className="mt-2 text-[11px] text-emerald-500/80">
                    Click card to open live view
                  </p>
                ) : null}

                {canTest ? (
                  <div
                    className="mt-4 border-t border-zinc-800 pt-3"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      type="button"
                      disabled={isTesting}
                      onClick={() => void handleTest(c.id)}
                      className="flex w-full items-center justify-center gap-2 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
                    >
                      {isTesting ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          Testing…
                        </>
                      ) : (
                        <>
                          <Activity className="h-3.5 w-3.5" />
                          Test connection
                        </>
                      )}
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      {liveCamera ? (
        <LiveViewPanel
          cameraName={liveCamera.name}
          streamName={process.env.NEXT_PUBLIC_GO2RTC_STREAM ?? "cam_v380"}
          onClose={() => setLiveCamera(null)}
        />
      ) : null}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3">
      <p className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-zinc-100">{value}</p>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-zinc-400">{label}</label>
      <input
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
      />
    </div>
  );
}