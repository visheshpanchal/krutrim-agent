import type {
  ChatApiMessage,
  EmbedRequest,
  EmbedResponse,
  RagDocument,
  RagTextResponse,
  SessionInfo,
  SessionSandboxPolicyUpdate,
  UpdateSessionRequest,
  WorkspaceFile,
} from '@krutrim_agent/shared-types';

import { apiDelete, apiGet, apiGetBlob, apiPost, apiPostForm, apiPut } from '../utils/http-client';
import {
  embedResponseSchema,
  ragDocumentsResponseSchema,
  ragTextResponseSchema,
  sessionInfoSchema,
  sessionMessagesResponseSchema,
  workspaceFilesResponseSchema,
} from './schemas';

/** `GET /api/sessions/{sessionId}` — sessions are addressed by id alone (globally unique). */
export function fetchSession(backendUrl: string, sessionId: string): Promise<SessionInfo> {
  return apiGet(`${backendUrl}/api/sessions/${sessionId}`, sessionInfoSchema);
}

/** `PUT /api/sessions/{sessionId}` — rename. */
export function updateSession(
  backendUrl: string,
  sessionId: string,
  body: UpdateSessionRequest,
): Promise<SessionInfo> {
  return apiPut(`${backendUrl}/api/sessions/${sessionId}`, sessionInfoSchema, body);
}

/** `DELETE /api/sessions/{sessionId}` */
export function deleteSession(backendUrl: string, sessionId: string): Promise<void> {
  return apiDelete(`${backendUrl}/api/sessions/${sessionId}`);
}

/** `GET /api/sessions/{sessionId}/messages` — reload a past conversation's visible turns.
 * Works for both `Chat`-owned sessions and `Agent`-owned ones (`research` etc.): the backend
 * reads the session's LangGraph checkpoint — for an in-sandbox agent that's the container run's
 * checkpoint synced back on release — and reduces it to user/assistant turns. */
export async function fetchSessionMessages(backendUrl: string, sessionId: string): Promise<ChatApiMessage[]> {
  const data = await apiGet(`${backendUrl}/api/sessions/${sessionId}/messages`, sessionMessagesResponseSchema);
  return data.messages;
}

/** `PUT /api/sessions/{sessionId}/sandbox-policy` */
export function updateSessionSandboxPolicy(
  backendUrl: string,
  sessionId: string,
  update: SessionSandboxPolicyUpdate,
): Promise<SessionInfo> {
  return apiPut(`${backendUrl}/api/sessions/${sessionId}/sandbox-policy`, sessionInfoSchema, update);
}

/** `POST /api/sessions/{sessionId}/embed` — dispatches the embedding precompute job. */
export function triggerEmbed(backendUrl: string, sessionId: string, body: EmbedRequest): Promise<EmbedResponse> {
  return apiPost(`${backendUrl}/api/sessions/${sessionId}/embed`, embedResponseSchema, body);
}

/** `POST /api/sessions/{sessionId}/rag/file` — real (binary-capable) document
 * upload: PDF, DOCX, and anything else `krutrim_agent_doc`'s parser registry
 * supports, not just plain text. Response shape is identical to `/rag/text`'s. */
export function submitRagFile(
  backendUrl: string,
  sessionId: string,
  file: File,
  title?: string | null,
): Promise<RagTextResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (title) formData.append('title', title);
  return apiPostForm(`${backendUrl}/api/sessions/${sessionId}/rag/file`, ragTextResponseSchema, formData);
}

/** `GET /api/sessions/{sessionId}/rag/documents` — every document ingested into
 * this session's RAG index, oldest first. Feeds the persistent attachment bar. */
export async function fetchSessionRagDocuments(backendUrl: string, sessionId: string): Promise<RagDocument[]> {
  const data = await apiGet(`${backendUrl}/api/sessions/${sessionId}/rag/documents`, ragDocumentsResponseSchema);
  return data.documents;
}

/** `DELETE /api/sessions/{sessionId}/rag/documents/{documentId}` — removes the
 * document from the session manifest (indexed vectors are swept on session delete). */
export function deleteSessionRagDocument(backendUrl: string, sessionId: string, documentId: string): Promise<void> {
  return apiDelete(`${backendUrl}/api/sessions/${sessionId}/rag/documents/${documentId}`);
}

/** `GET /api/sessions/{sessionId}/files` — the files the agent has saved into
 * this session's `/workspace` (deliverables, scratchpad, ingested uploads),
 * each with size + last-modified time, sorted by path. */
export async function fetchSessionWorkspaceFiles(
  backendUrl: string,
  sessionId: string,
): Promise<WorkspaceFile[]> {
  const data = await apiGet(`${backendUrl}/api/sessions/${sessionId}/files`, workspaceFilesResponseSchema);
  return data.files;
}

/** `GET /api/sessions/{sessionId}/files/{path}` — the raw bytes of one workspace
 * file (served as an attachment). `path` is `/workspace`-relative, posix-style. */
export function fetchWorkspaceFileBlob(backendUrl: string, sessionId: string, path: string): Promise<Blob> {
  const encoded = path.split('/').map(encodeURIComponent).join('/');
  return apiGetBlob(`${backendUrl}/api/sessions/${sessionId}/files/${encoded}`);
}
