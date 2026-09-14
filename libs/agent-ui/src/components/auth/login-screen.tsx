import { type FormEvent, useState } from 'react';
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label } from '@krutrim_agent/ui';

import { login, register } from '../../api';
import { setTokens } from '../../utils/auth-store';
import { ApiError } from '../../utils/http-client';

type Mode = 'login' | 'register';

interface LoginScreenProps {
  backendUrl: string;
  /** Called after tokens are stored, so `<AuthGate>` can re-render the app. */
  onAuthenticated: () => void;
}

/**
 * The only screen an unauthenticated visitor sees. Two modes on one form —
 * "Sign in" and "Create account" — both hitting `/api/auth/*` and, on
 * success, writing the token pair to `auth-store` and calling
 * `onAuthenticated`.
 */
export function LoginScreen({ backendUrl, onAuthenticated }: LoginScreenProps) {
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result =
        mode === 'login'
          ? await login(backendUrl, { username, password })
          : await register(backendUrl, { username, password });
      setTokens(result.tokens);
      onAuthenticated();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : `Could not reach the backend at ${backendUrl}.`,
      );
      setBusy(false);
    }
  }

  const isRegister = mode === 'register';

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{isRegister ? 'Create your account' : 'Sign in'}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={submit}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="auth-username">Username</Label>
              <Input
                id="auth-username"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                minLength={3}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="auth-password">Password</Label>
              <Input
                id="auth-password"
                type="password"
                autoComplete={isRegister ? 'new-password' : 'current-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
              />
            </div>

            {error && (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                {error}
              </p>
            )}

            <Button type="submit" disabled={busy}>
              {busy ? 'Please wait…' : isRegister ? 'Create account' : 'Sign in'}
            </Button>
          </form>

          <p className="mt-4 text-center text-xs text-muted-foreground">
            {isRegister ? 'Already have an account?' : "Don't have an account?"}{' '}
            <button
              type="button"
              className="font-medium text-primary hover:underline"
              onClick={() => {
                setMode(isRegister ? 'login' : 'register');
                setError(null);
              }}
            >
              {isRegister ? 'Sign in' : 'Create one'}
            </button>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
