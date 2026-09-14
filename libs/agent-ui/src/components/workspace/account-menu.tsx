import { useEffect, useState } from 'react';
import type { AuthUser } from '@krutrim_agent/shared-types';
import {
  Avatar,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@krutrim_agent/ui';
import { ChevronsUpDown, LogOut, Settings } from 'lucide-react';

import { fetchMe, signOut } from '../../api';
import { hasSession, onAuthChange } from '../../utils/auth-store';
import AppearanceControl from '../settings/workspace-settings/AppearanceControl';
import { AppSettingsSection } from '../settings/workspace-settings/app-settings-section';

interface AccountMenuProps {
  backendUrl: string;
}

/**
 * The account control pinned to the bottom of the workspace rail. The row opens a
 * menu whose **Settings** item opens a centred, screen-level dialog of
 * application-wide preferences — nothing agent- or chat-scoped. Model / sandbox
 * settings live in the thread headers instead.
 */
export function AccountMenu({ backendUrl }: AccountMenuProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authed, setAuthed] = useState(hasSession());

  useEffect(() => onAuthChange(() => setAuthed(hasSession())), []);

  useEffect(() => {
    if (!authed) {
      setUser(null);
      return;
    }
    let cancelled = false;
    fetchMe(backendUrl)
      .then((u) => !cancelled && setUser(u))
      .catch(() => !cancelled && setUser(null));
    return () => {
      cancelled = true;
    };
  }, [backendUrl, authed]);

  const name = user?.username ?? 'Account';
  const sub = user?.email ?? (user ? `Signed in as ${user.role}` : 'Not signed in');

  return (
    <div className="border-t border-border p-2">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-secondary"
          >
            <Avatar label={name} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-foreground">{name}</span>
              <span className="block truncate text-xs text-muted-foreground">{sub}</span>
            </span>
            <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side="top" className="w-60">
          <DropdownMenuItem onSelect={() => setSettingsOpen(true)}>
            <Settings className="size-4" />
            Settings
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={!authed}
            onSelect={() => {
              void signOut(backendUrl);
            }}
          >
            <LogOut className="size-4" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent aria-describedby={undefined} className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Settings</DialogTitle>
          </DialogHeader>

          <div className="flex max-h-[70vh] flex-col gap-6 overflow-y-auto pr-1">
            <AppearanceControl />
            <AppSettingsSection backendUrl={backendUrl} />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
