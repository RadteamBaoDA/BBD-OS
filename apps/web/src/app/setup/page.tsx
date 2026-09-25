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

const setupSchema = z.object({ setupToken: z.string().min(1), password: z.string().min(12).max(128), confirmPassword: z.string() }).refine((value) => value.password === value.confirmPassword, { path: ['confirmPassword'], message: 'Passwords do not match' });
type SetupForm = z.infer<typeof setupSchema>;

export default function SetupPage() {
  const router = useRouter();
  const form = useForm<SetupForm>({ resolver: zodResolver(setupSchema) });
  const setup = useMutation({
    mutationFn: async (values: SetupForm) => {
      const csrf = await apiRequest<{ csrfToken: string }>('/api/v1/auth/csrf');
      return apiRequest<{ created: boolean }>('/api/v1/auth/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrf.csrfToken), 'X-Setup-Token': values.setupToken },
        body: JSON.stringify({ password: values.password }),
      });
    },
    onSuccess: () => router.replace('/login'),
  });

  return <main className="page"><section className="auth-panel"><span className="brand">BBD-OS · Local setup</span><h1>Create your owner account</h1><p className="muted">This account is stored on this server. Choose a password with at least 12 characters.</p><form className="form" onSubmit={form.handleSubmit((values) => setup.mutate(values))}>
    <div className="field"><Label htmlFor="setupToken">Setup token</Label><Input id="setupToken" autoComplete="off" {...form.register('setupToken')} />{form.formState.errors.setupToken && <span className="error">Enter the setup token.</span>}</div>
    <div className="field"><Label htmlFor="password">Password</Label><Input id="password" type="password" autoComplete="new-password" {...form.register('password')} />{form.formState.errors.password && <span className="error">Use 12 to 128 characters.</span>}</div>
    <div className="field"><Label htmlFor="confirmPassword">Confirm password</Label><Input id="confirmPassword" type="password" autoComplete="new-password" {...form.register('confirmPassword')} />{form.formState.errors.confirmPassword && <span className="error">{form.formState.errors.confirmPassword.message}</span>}</div>
    {setup.error && <p className="error" role="alert">{setup.error instanceof ApiError ? setup.error.message : 'Setup could not be completed.'}</p>}
    <Button type="submit" disabled={setup.isPending}>{setup.isPending ? 'Creating account…' : 'Create owner'}</Button>
  </form></section></main>;
}
