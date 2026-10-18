"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Camera } from "@/types/camera";
import {
  listVideoDevices,
  mediaErrorMessage,
  openWebcam,
  stopMediaStream,
  type VideoDevice,
} from "@/lib/mediaDevices";
import { statusDotClass, statusTextClass } from "@/features/cameras/statusStyles";

type Props = {
  camera: Camera;
  onClose: () => void;
};

export function CameraLiveModal({ camera, onClose }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [devices, setDevices] = useState<VideoDevice[]>([]);
  const [deviceId, setDeviceId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);

  const stopPreview = useCallback(() => {
    stopMediaStream(streamRef.current);
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setLive(false);
  }, []);

  const startPreview = useCallback(async (id?: string) => {
    setError(null);
    setLoading(true);
    stopPreview();
    try {
      const stream = await openWebcam(id || undefined);
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }
      setLive(true);
    } catch (err) {
      setError(mediaErrorMessage(err));
      setLive(false);
    } finally {
      setLoading(false);
    }
  }, [stopPreview]);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      setLoading(true);
      setError(null);
      try {
        const list = await listVideoDevices();
        if (cancelled) return;
        if (list.length === 0) {
          setDevices([]);
          setError("No camera is plugged in or available on this workstation");
          setLoading(false);
          return;
        }
        setDevices(list);
        const first = list[0].deviceId;
        setDeviceId(first);
        await startPreview(first);
      } catch (err) {
        if (!cancelled) {
          setError(mediaErrorMessage(err));
          setLoading(false);
        }
      }
    }

    void init();

    return () => {
      cancelled = true;
      stopPreview();
    };
  }, [startPreview, stopPreview]);

  async function onDeviceChange(nextId: string) {
    setDeviceId(nextId);
    await startPreview(nextId);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div
        className="absolute inset-0"
        onClick={onClose}
        aria-hidden
      />
      <div className="relative z-10 w-full max-w-3xl rounded-xl border border-zinc-800 bg-zinc-950 shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-zinc-800 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">{camera.name}</h2>
            <p className="mt-0.5 text-xs text-zinc-500">
              {camera.ipAddress} ({camera.protocol}) · {camera.cameraCode}
            </p>
            <div className="mt-2 flex items-center gap-2 text-xs">
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full ${statusDotClass(camera.status)}`}
              />
              <span className={statusTextClass(camera.status)}>{camera.status}</span>
              <span className="text-zinc-600">
                Live view uses this workstation webcam (demo until RTSP proxy)
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-900"
          >
            Close
          </button>
        </div>

        <div className="space-y-3 p-4">
          <div className="relative aspect-video overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900">
            <video
              ref={videoRef}
              className="h-full w-full object-contain"
              playsInline
              muted
              autoPlay
            />
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center bg-zinc-950/80 text-sm text-zinc-400">
                Checking cameras…
              </div>
            )}
            {!loading && error && (
              <div className="absolute inset-0 flex items-center justify-center bg-zinc-950/90 px-6 text-center text-sm text-red-300">
                {error}
              </div>
            )}
            {!loading && !error && live && (
              <span className="absolute left-2 top-2 rounded bg-red-600/90 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-white">
                LIVE
              </span>
            )}
          </div>

          {devices.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-xs text-zinc-500">Device</label>
              <select
                value={deviceId}
                onChange={(e) => void onDeviceChange(e.target.value)}
                className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-xs text-zinc-100"
              >
                {devices.map((d) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void startPreview(deviceId)}
                className="rounded-md border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-300 hover:bg-zinc-900"
              >
                Restart preview
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
