import { apiRequest } from "@/lib/api";
import type {
  CreateCustodyEventRequest,
  CustodyEvent,
  CustodyEventListResponse,
  EvidenceTransfer,
  InitiateTransferRequest,
  TransferDecisionRequest,
} from "@/types/custody";

function idempotencyKey(): string {
  return (crypto.randomUUID() + crypto.randomUUID()).replace(/-/g, "").slice(0, 32);
}

function requireId(id: string, label: string): void {
  if (!id?.trim()) throw new Error(`${label} is required`);
}

export async function listCustodyEvents(
  evidenceId: string,
  page = 1,
  pageSize = 25,
): Promise<CustodyEventListResponse> {
  requireId(evidenceId, "Evidence id");
  const safePage = Math.max(1, page);
  const safeSize = Math.min(100, Math.max(1, pageSize));
  const q = new URLSearchParams({
    page: String(safePage),
    page_size: String(safeSize),
  });
  try {
    return await apiRequest<CustodyEventListResponse>(
      `/api/v1/evidence/${evidenceId}/custody-events?${q}`,
    );
  } catch (e) {
    throw new Error(
      e instanceof Error ? e.message : "Failed to load custody events",
    );
  }
}

export async function createCustodyEvent(
  evidenceId: string,
  body: CreateCustodyEventRequest,
): Promise<CustodyEvent> {
  requireId(evidenceId, "Evidence id");
  if (!body.eventType?.trim()) {
    throw new Error("Event type is required");
  }
  try {
    return await apiRequest<CustodyEvent>(
      `/api/v1/evidence/${evidenceId}/custody-events`,
      {
        method: "POST",
        headers: {
          "Idempotency-Key": idempotencyKey(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          eventType: body.eventType,
          purpose: body.purpose?.trim() || null,
          eventMetadata: body.eventMetadata ?? {},
        }),
      },
    );
  } catch (e) {
    throw new Error(
      e instanceof Error ? e.message : "Failed to create custody event",
    );
  }
}

export async function initiateEvidenceTransfer(
  evidenceId: string,
  body: InitiateTransferRequest,
): Promise<EvidenceTransfer> {
  requireId(evidenceId, "Evidence id");
  requireId(body.toUserId, "Recipient");
  if (!body.purpose?.trim() || body.purpose.trim().length < 3) {
    throw new Error("Purpose must be at least 3 characters");
  }
  try {
    return await apiRequest<EvidenceTransfer>(
      `/api/v1/evidence/${evidenceId}/transfers`,
      {
        method: "POST",
        headers: {
          "Idempotency-Key": idempotencyKey(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          toUserId: body.toUserId,
          purpose: body.purpose.trim(),
          ...(body.expiresAt ? { expiresAt: body.expiresAt } : {}),
        }),
      },
    );
  } catch (e) {
    throw new Error(
      e instanceof Error ? e.message : "Failed to initiate transfer",
    );
  }
}

export async function acceptEvidenceTransfer(
  evidenceId: string,
  transferId: string,
  body: TransferDecisionRequest = {},
): Promise<EvidenceTransfer> {
  requireId(evidenceId, "Evidence id");
  requireId(transferId, "Transfer id");
  try {
    return await apiRequest<EvidenceTransfer>(
      `/api/v1/evidence/${evidenceId}/transfers/${transferId}/accept`,
      {
        method: "POST",
        headers: {
          "Idempotency-Key": idempotencyKey(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ comment: body.comment?.trim() || null }),
      },
    );
  } catch (e) {
    throw new Error(
      e instanceof Error ? e.message : "Failed to accept transfer",
    );
  }
}

export async function rejectEvidenceTransfer(
  evidenceId: string,
  transferId: string,
  body: TransferDecisionRequest = {},
): Promise<EvidenceTransfer> {
  requireId(evidenceId, "Evidence id");
  requireId(transferId, "Transfer id");
  try {
    return await apiRequest<EvidenceTransfer>(
      `/api/v1/evidence/${evidenceId}/transfers/${transferId}/reject`,
      {
        method: "POST",
        headers: {
          "Idempotency-Key": idempotencyKey(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ comment: body.comment?.trim() || null }),
      },
    );
  } catch (e) {
    throw new Error(
      e instanceof Error ? e.message : "Failed to reject transfer",
    );
  }
}