import { ReportFiles } from '../../components/workspace/report-files';
import { ProseMarkdown } from '../default/prose';
import type { ScreenOutputRendererProps } from '../types';

/**
 * Renders a chat deliverable (see `chat-split.ts`'s `===OUTPUT===` marker) as
 * plain markdown — chat deliverables don't follow the research markdown-export
 * spec's section-marker/TOC/math conventions, so no `ResearchRenderer`-style
 * preprocessing is needed. Mounts the same `ReportFiles` strip research uses
 * for listing/downloading the session's saved workspace files.
 */
export function ChatRenderer({ payload, session }: ScreenOutputRendererProps) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="border-b border-border px-6 py-4">
        <span className="mb-1 block font-mono text-xs uppercase tracking-widest text-primary">Output</span>
        <h2 className="font-mono text-xl font-semibold text-foreground">{payload.title}</h2>
      </header>

      {session && (
        <ReportFiles
          backendUrl={session.backendUrl}
          sessionId={session.sessionId}
          isRunning={session.isRunning}
          onExport={() => session.sendMessage('Please export this as a PDF file using the document-export skill.')}
        />
      )}

      <div className="min-w-0 flex-1 overflow-y-auto px-6 py-6 lg:px-8">
        <ProseMarkdown content={payload.content} />
      </div>
    </div>
  );
}
