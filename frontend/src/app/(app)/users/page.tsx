"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { createUser, listUsers } from "@/features/users/api";
import { ROLE_OPTIONS } from "@/features/users/roles";
import { Users, UserPlus, Shield } from "lucide-react";

type UserRow = {
  id: string;
  email: string;
  username: string;
  firstName?: string;
  lastName?: string;
  isActive?: boolean;
  roles?: string[];
};

function normalizeUsers(data: unknown): UserRow[] {
  if (Array.isArray(data)) {
    return data as UserRow[];
  }
  if (data && typeof data === "object" && "items" in data) {
    const items = (data as { items?: unknown }).items;
    if (Array.isArray(items)) {
      return items as UserRow[];
    }
  }
  return [];
}

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);

  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [roleId, setRoleId] = useState(ROLE_OPTIONS[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setListLoading(true);
    setListError(null);
    try {
      const data = await listUsers();
      setUsers(normalizeUsers(data));
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to load users");
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);
    try {
      await createUser({
        email,
        username,
        password,
        firstName,
        lastName,
        phone: phone || undefined,
        roleIds: [roleId],
      });
      setSuccess(`Created user ${username}`);
      setPassword("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setLoading(false);
    }
  }

  const activeCount = users.filter((u) => u.isActive !== false).length;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Administration
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-50">Users</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Directory and Accounts Provisioning ·  
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          className="rounded-md border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500"
        >
          Refresh
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        {(
          [
            { label: "Total users", value: users.length, icon: Users },
            { label: "Active", value: activeCount, icon: Shield },
            {
              label: "Role templates",
              value: ROLE_OPTIONS.length,
              icon: UserPlus,
            },
          ] as const
        ).map(({ label, value, icon: Icon }) => (
          <div
            key={label}
            className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4"
          >
            <div className="flex items-center justify-between">
              <p className="text-xs uppercase tracking-wide text-zinc-500">
                {label}
              </p>
              <Icon className="h-4 w-4 text-zinc-500" />
            </div>
            <p className="mt-2 text-2xl font-semibold text-zinc-50">{value}</p>
          </div>
        ))}
      </div>

      {/* Directory + create */}
      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <section className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/60">
          <div className="border-b border-zinc-800 px-4 py-3">
            <h2 className="text-sm font-medium text-zinc-100">Directory</h2>
            <p className="text-xs text-zinc-500">
              Accounts in this environment
            </p>
          </div>
          {listLoading ? (
            <p className="p-4 text-sm text-zinc-500">Loading…</p>
          ) : listError ? (
            <p className="p-4 text-sm text-red-400">{listError}</p>
          ) : users.length === 0 ? (
            <p className="p-4 text-sm text-zinc-500">No users returned.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-zinc-800 text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">User</th>
                    <th className="px-4 py-2 font-medium">Roles</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/80">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-zinc-800/40">
                      <td className="px-4 py-3">
                        <p className="font-medium text-zinc-200">
                          {u.username}
                        </p>
                        <p className="text-xs text-zinc-500">{u.email}</p>
                      </td>
                      <td className="px-4 py-3 text-xs text-zinc-400">
                        {(u.roles ?? []).join(", ") || "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={
                            u.isActive === false
                              ? "text-xs text-red-400"
                              : "text-xs text-emerald-400"
                          }
                        >
                          {u.isActive === false ? "Inactive" : "Active"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="h-fit rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="text-sm font-medium text-zinc-100">Create user</h2>
          <p className="mb-4 mt-0.5 text-xs text-zinc-500">
            Provisions an account and assigns one role
          </p>

          <form onSubmit={onSubmit} className="space-y-3">
            {(
              [
                ["Email", email, setEmail, "email"],
                ["Username", username, setUsername, "text"],
                ["Password", password, setPassword, "password"],
                ["First name", firstName, setFirstName, "text"],
                ["Last name", lastName, setLastName, "text"],
                ["Phone", phone, setPhone, "text"],
              ] as const
            ).map(([label, value, set, type]) => (
              <div key={label}>
                <label className="mb-1 block text-xs text-zinc-400">
                  {label}
                </label>
                <input
                  type={type}
                  required={label !== "Phone"}
                  value={value}
                  onChange={(e) => set(e.target.value)}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
                />
              </div>
            ))}

            <div>
              <label className="mb-1 block text-xs text-zinc-400">Role</label>
              <select
                value={roleId}
                onChange={(e) => setRoleId(e.target.value)}
                className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </div>

            {error ? (
              <p className="text-sm text-red-400" role="alert">
                {error}
              </p>
            ) : null}
            {success ? (
              <p className="text-sm text-emerald-400">{success}</p>
            ) : null}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-md bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-60"
            >
              {loading ? "Creating…" : "Create user"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}