import {
  Activity,
  AlertTriangle,
  Camera,
  CheckCircle2,
  Clock3,
  Database,
  FileCheck2,
  Server,
  ShieldCheck,
  Users,
  Wifi,
  WifiOff,
} from "lucide-react"

const stats = [
  {
    label: "Connected cameras",
    value: "12 / 14",
    detail: "2 cameras require attention",
    icon: Camera,
    status: "warning",
  },
  {
    label: "Detections · 24h",
    value: "284",
    detail: "+18.4% from previous period",
    icon: Activity,
    status: "normal",
  },
  {
    label: "Open incidents",
    value: "7",
    detail: "3 require immediate review",
    icon: AlertTriangle,
    status: "danger",
  },
  {
    label: "Evidence items",
    value: "1,842",
    detail: "Integrity checks operational",
    icon: Database,
    status: "normal",
  },
]

const activities = [
  {
    time: "19:03:41",
    camera: "CAM-07",
    event: "Person detected",
    confidence: "96%",
    type: "Detection",
  },
  {
    time: "18:58:12",
    camera: "CAM-02",
    event: "Vehicle detected",
    confidence: "91%",
    type: "Detection",
  },
  {
    time: "18:51:06",
    camera: "CAM-11",
    event: "Motion detected",
    confidence: "88%",
    type: "Detection",
  },
  {
    time: "18:42:33",
    camera: "CAM-04",
    event: "Incident created",
    confidence: "—",
    type: "Incident",
  },
  {
    time: "18:37:19",
    camera: "CAM-09",
    event: "Person detected",
    confidence: "94%",
    type: "Detection",
  },
]

const incidents = [
  {
    id: "INC-2026-0042",
    title: "Unauthorised access detected",
    camera: "CAM-04",
    priority: "High",
    status: "Open",
    time: "18:42",
  },
  {
    id: "INC-2026-0041",
    title: "Vehicle in restricted area",
    camera: "CAM-02",
    priority: "Medium",
    status: "Investigating",
    time: "17:56",
  },
  {
    id: "INC-2026-0039",
    title: "After-hours movement",
    camera: "CAM-09",
    priority: "Medium",
    status: "Open",
    time: "16:31",
  },
  {
    id: "INC-2026-0037",
    title: "Camera obstruction",
    camera: "CAM-11",
    priority: "Low",
    status: "Review",
    time: "15:08",
  },
]

const cameras = [
  { id: "CAM-01", name: "Main Entrance", status: "Online", latency: "42ms" },
  { id: "CAM-02", name: "North Gate", status: "Online", latency: "38ms" },
  { id: "CAM-03", name: "Parking Area", status: "Online", latency: "51ms" },
  { id: "CAM-04", name: "Restricted Access", status: "Online", latency: "44ms" },
  { id: "CAM-05", name: "Warehouse", status: "Offline", latency: "—" },
  { id: "CAM-06", name: "Rear Entrance", status: "Online", latency: "47ms" },
]

function statusClasses(status: string) {
  switch (status) {
    case "danger":
      return "text-red-400 bg-red-400/10 border-red-400/20"
    case "warning":
      return "text-amber-400 bg-amber-400/10 border-amber-400/20"
    default:
      return "text-emerald-400 bg-emerald-400/10 border-emerald-400/20"
  }
}

function priorityClasses(priority: string) {
  switch (priority) {
    case "High":
      return "text-red-400 bg-red-400/10"
    case "Medium":
      return "text-amber-400 bg-amber-400/10"
    default:
      return "text-zinc-400 bg-zinc-800"
  }
}

export default function DashboardPage() {
  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Operations
          </p>

          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-50">
            Dashboard
          </h1>

          <p className="mt-1 text-sm text-zinc-500">
            Monitor · Detect · Investigate · Preserve
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900/70 px-3 py-2 text-xs">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="text-zinc-300">All core services operational</span>
        </div>
      </div>

      {/* KPI cards */}
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon

          return (
            <div
              key={stat.label}
              className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 transition hover:border-zinc-700"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                    {stat.label}
                  </p>

                  <p className="mt-3 text-2xl font-semibold text-zinc-50">
                    {stat.value}
                  </p>
                </div>

                <div
                  className={`rounded-md border p-2 ${statusClasses(stat.status)}`}
                >
                  <Icon className="h-4 w-4" />
                </div>
              </div>

              <p className="mt-3 text-xs text-zinc-500">{stat.detail}</p>
            </div>
          )
        })}
      </section>

      {/* Activity + incidents */}
      <section className="grid gap-4 xl:grid-cols-[1.35fr_1fr]">
        <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/60">
          <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
            <div>
              <h2 className="text-sm font-medium text-zinc-100">
                Live activity
              </h2>
              <p className="mt-0.5 text-xs text-zinc-500">
                Recent detection and incident events
              </p>
            </div>

            <Activity className="h-4 w-4 text-zinc-500" />
          </div>

          <div className="divide-y divide-zinc-800/70">
            {activities.map((activity) => (
              <div
                key={`${activity.time}-${activity.camera}`}
                className="flex items-center gap-4 px-4 py-3"
              >
                <div className="w-16 shrink-0 text-xs text-zinc-600">
                  {activity.time}
                </div>

                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-zinc-800">
                  {activity.type === "Incident" ? (
                    <AlertTriangle className="h-4 w-4 text-amber-400" />
                  ) : (
                    <Activity className="h-4 w-4 text-blue-400" />
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-zinc-200">
                    {activity.event}
                  </p>
                  <p className="text-xs text-zinc-600">{activity.camera}</p>
                </div>

                <div className="text-right">
                  <p className="text-xs text-zinc-400">{activity.type}</p>
                  <p className="mt-0.5 text-xs text-zinc-600">
                    {activity.confidence}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/60">
          <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
            <div>
              <h2 className="text-sm font-medium text-zinc-100">
                Recent incidents
              </h2>
              <p className="mt-0.5 text-xs text-zinc-500">
                Cases requiring investigation
              </p>
            </div>

            <ShieldCheck className="h-4 w-4 text-zinc-500" />
          </div>

          <div className="divide-y divide-zinc-800/70">
            {incidents.map((incident) => (
              <div key={incident.id} className="px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-zinc-200">
                      {incident.title}
                    </p>

                    <div className="mt-1 flex items-center gap-2 text-xs text-zinc-600">
                      <span>{incident.id}</span>
                      <span>·</span>
                      <span>{incident.camera}</span>
                      <span>·</span>
                      <span>{incident.time}</span>
                    </div>
                  </div>

                  <span
                    className={`shrink-0 rounded px-2 py-1 text-[10px] font-medium ${priorityClasses(
                      incident.priority,
                    )}`}
                  >
                    {incident.priority}
                  </span>
                </div>

                <div className="mt-2 flex items-center gap-2">
                  <span className="rounded bg-zinc-800 px-2 py-1 text-[10px] text-zinc-400">
                    {incident.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Camera status */}
      <section className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/60">
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <div>
            <h2 className="text-sm font-medium text-zinc-100">
              Camera status
            </h2>
            <p className="mt-0.5 text-xs text-zinc-500">
              Current connectivity and stream health
            </p>
          </div>

          <Camera className="h-4 w-4 text-zinc-500" />
        </div>

        <div className="grid gap-px bg-zinc-800 sm:grid-cols-2 lg:grid-cols-3">
          {cameras.map((camera) => {
            const online = camera.status === "Online"

            return (
              <div key={camera.id} className="bg-zinc-900 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-200">
                      {camera.id}
                    </p>
                    <p className="mt-0.5 text-xs text-zinc-600">
                      {camera.name}
                    </p>
                  </div>

                  {online ? (
                    <Wifi className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <WifiOff className="h-4 w-4 text-red-400" />
                  )}
                </div>

                <div className="mt-4 flex items-center justify-between">
                  <span
                    className={`flex items-center gap-1.5 text-xs ${
                      online ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        online ? "bg-emerald-400" : "bg-red-400"
                      }`}
                    />
                    {camera.status}
                  </span>

                  <span className="text-xs text-zinc-600">
                    {camera.latency}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* System status */}
      <section className="grid gap-4 md:grid-cols-3">
        <div className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <div className="rounded-md bg-emerald-400/10 p-2 text-emerald-400">
            <Server className="h-4 w-4" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">API service</p>
            <p className="text-sm text-zinc-200">Operational</p>
          </div>
          <CheckCircle2 className="ml-auto h-4 w-4 text-emerald-400" />
        </div>

        <div className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <div className="rounded-md bg-emerald-400/10 p-2 text-emerald-400">
            <FileCheck2 className="h-4 w-4" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Evidence integrity</p>
            <p className="text-sm text-zinc-200">Verified</p>
          </div>
          <CheckCircle2 className="ml-auto h-4 w-4 text-emerald-400" />
        </div>

        <div className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <div className="rounded-md bg-blue-400/10 p-2 text-blue-400">
            <Clock3 className="h-4 w-4" />
          </div>
          <div>
            <p className="text-xs text-zinc-500">Last system check</p>
            <p className="text-sm text-zinc-200">Just now</p>
          </div>
          <span className="ml-auto text-xs text-zinc-600">UTC</span>
        </div>
      </section>
    </div>
  )
}
