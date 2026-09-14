import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@krutrim_agent/ui';
import { Download, FileText, Loader2, RefreshCw } from 'lucide-react';
import type { WorkspaceFile } from '@krutrim_agent/shared-types';

import { fetchSessionWorkspaceFiles, fetchWorkspaceFileBlob } from '../../api';

export interface ReportFilesProps {
  backendUrl: string;
  sessionId: string;
  /** A run is in flight — the list refetches when this flips back to false. */
  isRunning: boolean;
  /** Send a follow-up asking the agent to export the report. */
  onExport: (format: 'pdf') => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Top-level deliverables only — hide the `.research/` scratchpad, RAG upload
 * staging (`_rag_uploads/…`), and the export skill's staged helper. */
function isDeliverable(path: string): boolean {
  return !path.includes('/') && !path.startsWith('.') && path !== 'md_export.py';
}

/**
 * A compact strip above the research report listing the files the agent saved
 * into this session's `/workspace` (`GET /api/sessions/{id}/files`), each with a
 * download button, plus "Export PDF / DOCX" affordances that send a follow-up
 * message triggering the `document-export` skill. Only the research screen
 * mounts this.
 */
export function ReportFiles({ backendUrl, sessionId, isRunning, onExport }: ReportFilesProps) {
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const wasRunningRef = useRef(isRunning);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchSessionWorkspaceFiles(backendUrl, sessionId)
      .then((all) => setFiles(all.filter((f) => isDeliverable(f.path))))
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load files.'))
      .finally(() => setLoading(false));
  }, [backendUrl, sessionId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  // Refresh once a run finishes — that's when a new report / export lands.
  useEffect(() => {
    if (wasRunningRef.current && !isRunning) refetch();
    wasRunningRef.current = isRunning;
  }, [isRunning, refetch]);

  async function download(file: WorkspaceFile) {
    setDownloading(file.path);
    try {
      const blob = await fetchWorkspaceFileBlob(backendUrl, sessionId, file.path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.path;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed.');
    } finally {
      setDownloading(null);
    }
  }

  const hasMarkdown = files.some((f) => f.path.endsWith('.md'));
  if (!loading && !error && files.length === 0) return null;

  return (
    <section className="border-b border-border bg-muted/20 px-6 py-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Files</span>
        <button
          type="button"
          onClick={refetch}
          disabled={loading}
          aria-label="Refresh file list"
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          {loading ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
        </button>
      </div>

      {error && <p className="mb-2 text-xs text-destructive">{error}</p>}

      <ul className="flex flex-col gap-1">
        {files.map((file) => (
          <li
            key={file.path}
            className="flex items-center gap-2 rounded-md border border-border bg-background px-2.5 py-1.5"
          >
            <FileText className="size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate text-sm text-foreground">{file.path}</span>
            <span className="shrink-0 font-mono text-xs text-muted-foreground">{formatBytes(file.size)}</span>
            <button
              type="button"
              onClick={() => download(file)}
              disabled={downloading === file.path}
              aria-label={`Download ${file.path}`}
              className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              {downloading === file.path ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Download className="size-4" />
              )}
            </button>
          </li>
        ))}
      </ul>

      {hasMarkdown && (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Export:</span>
          <Button size="sm" variant="outline" disabled={isRunning} onClick={() => onExport('pdf')}>
            PDF
          </Button>
        </div>
      )}
    </section>
  );
}
