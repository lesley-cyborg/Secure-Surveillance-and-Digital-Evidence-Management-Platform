"use client";

type LiveViewPanelProps = {
  cameraName: string;
  streamName?: string;
  onClose: () => void;
};

export function LiveViewPanel({
  cameraName,
  streamName,
  onClose,
}: LiveViewPanelProps) {
  const base =
    process.env.NEXT_PUBLIC_GO2RTC_BASE?.replace(/\/$/, "") ??
    "http://127.0.0.1:1984";
  const stream =
    streamName ?? process.env.NEXT_PUBLIC_GO2RTC_STREAM ?? "cam_v380";

  const src = `${base}/stream.html?src=${encodeURIComponent(stream)}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="flex w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950 shadow-xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <div>
            <p className="text-sm font-medium text-zinc-100">{cameraName}</p>
            <p className="text-xs text-zinc-500">
              Live via go2rtc · stream{" "}
              <span className="font-mono text-zinc-400">{stream}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            Close
          </button>
        </div>

        <div className="aspect-video w-full bg-black">
          <iframe
            title={`Live ${cameraName}`}
            src={src}
            className="h-full w-full border-0"
            allow="autoplay; fullscreen"
          />
        </div>

        <p className="border-t border-zinc-800 px-4 py-2 text-[11px] text-zinc-600">
          RTSP stays on the server. Browser only talks to go2rtc at {base}.
        </p>
      </div>
    </div>
  );
}