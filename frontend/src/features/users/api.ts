import { apiRequest } from "@/lib/api";
import type { CreateUserRequest } from "@/types/user";

export async function listUsers() {
  return apiRequest<{ items: Array<{ id: string; email: string; username?: string }> }>(
    "/api/v1/users",
  );
}

export async function getUser(userId: string) {
  return apiRequest<unknown>(`/api/v1/users/${userId}`);
}

export async function createUser(body: CreateUserRequest) {
  return apiRequest("/api/v1/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function assignRole(userId: string, roleId: string) {
  return apiRequest(`/api/v1/users/${userId}/roles/${roleId}`, {
    method: "POST",
  });
}

export async function removeRole(userId: string, roleId: string) {
  return apiRequest(`/api/v1/users/${userId}/roles/${roleId}`, {
    method: "DELETE",
  });
}