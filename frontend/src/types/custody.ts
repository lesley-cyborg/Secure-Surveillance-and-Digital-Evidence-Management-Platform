export type TransferStatus =
  | "PENDING"
  | "ACCEPTED"
  | "REJECTED"
  | "EXPIRED"
  | "CANCELLED"
  | string;

export type CustodyEventType =
  | "ACQUIRED"
  | "VIEWED"
  | "TRANSFER_INITIATED"
  | "TRANSFER_ACCEPTED"
  | "TRANSFER_REJECTED"
  | "EXPORTED"
  | string;

export type InitiateTransferRequest = {
  toUserId: string;
  purpose: string;
  expiresAt?: string | null;
};

export type EvidenceTransfer = {
  id: string;
  evidenceId: string;
  fromUserId: string;
  toUserId: string;
  purpose: string;
  status: TransferStatus;
  createdAt: string;
  decidedAt?: string | null;
};

export type TransferDecisionRequest = {
  comment?: string | null;
};

export type CustodyEvent = {
  id: string;
  evidenceId: string;
  actorUserId?: string | null;
  fromUserId?: string | null;
  toUserId?: string | null;
  previousRecordId?: string | null;
  eventType: CustodyEventType;
  purpose?: string | null;
  sourceIp?: string | null;
  deviceIdentifier?: string | null;
  eventMetadata?: Record<string, unknown> | null;
  recordHash?: string | null;
  digitalSignature?: string | null;
  occurredAt: string;
};

export type PaginationMeta = {
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
  hasNext: boolean;
  hasPrevious: boolean;
};

export type CustodyEventListResponse = {
  items: CustodyEvent[];
  pagination: PaginationMeta;
};

export type CreateCustodyEventRequest = {
  eventType: CustodyEventType;
  purpose?: string | null;
  eventMetadata?: Record<string, unknown> | null;
};