'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { ApiError, apiRequest, csrfHeaders } from '@/core/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const loginSchema = z.object({ password: z.string().min(1).max(128) });
type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const form = useForm<LoginForm>({ resolver: zodResolver(loginSchema) });
  const login = useMutation({
    mutationFn: async (values: LoginForm) => {
      const csrf = await apiRequest<{ csrfToken: string }>('/api/v1/auth/csrf');
      return apiRequest<{ authenticated: boolean }>('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrf.csrfToken) },
        body: JSON.stringify(values),
      });
    },
    onSuccess: () => router.replace('/app'),
  });

  return <main className="page"><section className="auth-panel"><span className="brand">BBD-OS</span><h1>Welcome back</h1><p className="muted">Sign in to your private workspace.</p><form className="form" onSubmit={form.handleSubmit((values) => login.mutate(values))}>
    <div className="field"><Label htmlFor="password">Password</Label><Input id="password" type="password" autoComplete="current-password" autoFocus {...form.register('password')} />{form.formState.errors.password && <span className="error">Enter your password.</span>}</div>
    {login.error && <p className="error" role="alert">{login.error instanceof ApiError ? login.error.message : 'Sign in could not be completed.'}</p>}
    <Button type="submit" disabled={login.isPending}>{login.isPending ? 'Signing in…' : 'Sign in'}</Button>
  </form></section></main>;
}
