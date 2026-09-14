import { type ReactNode, useEffect, useState } from 'react';

import { fetchAuthConfig } from '../../api';
import { hasSession, onAuthChange } from '../../utils/auth-store';
import { LoginScreen } from './login-screen';

interface AuthGateProps {
  backendUrl: string;
  children: ReactNode;
}

type Phase =
  | { kind: 'checking' }
  | { kind: 'error'; message: string }
  | { kind: 'open' } // auth disabled on the backend — no gate
  | { kind: 'authed' }
  | { kind: 'anon' };

/**
 * Wraps the app. On mount it asks the backend whether auth is enforced:
 *  - not enforced  -> render the app straight away.
 *  - enforced      -> render the app iff a token pair is in `auth-store`,
 *                     otherwise show `<LoginScreen>`.
 *
 * It re-renders on every `auth-store` change, so a fresh login shows the app
 * and a failed refresh (which clears the tokens) drops back to the login
 * screen with no manual routing.
 */
export function AuthGate({ backendUrl, children }: AuthGateProps) {
  const [phase, setPhase] = useState<Phase>({ kind: 'checking' });

  useEffect(() => {
    let cancelled = false;

    function resolve(enforced: boolean) {
      if (cancelled) return;
      if (!enforced) setPhase({ kind: 'open' });
      else setPhase({ kind: hasSession() ? 'authed' : 'anon' });
    }

    fetchAuthConfig(backendUrl)
      .then((cfg) => resolve(cfg.enabled))
      .catch(() => {
        if (!cancelled) {
          setPhase({
            kind: 'error',
            message: `Could not reach the backend at ${backendUrl}.`,
          });
        }
      });

    const unsub = onAuthChange(() => resolve(true));
    return () => {
      cancelled = true;
      unsub();
    };
  }, [backendUrl]);

  if (phase.kind === 'checking') {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (phase.kind === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <p className="max-w-sm rounded-md border border-destructive/40 bg-destructive/10 p-3 text-center text-sm text-destructive">
          {phase.message}
        </p>
      </div>
    );
  }

  if (phase.kind === 'anon') {
    return (
      <LoginScreen backendUrl={backendUrl} onAuthenticated={() => setPhase({ kind: 'authed' })} />
    );
  }

  return <>{children}</>;
}
