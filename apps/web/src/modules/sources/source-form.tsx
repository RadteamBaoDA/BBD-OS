'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ApiError } from '@/core/api';
import { useWorkspaceSession } from '@/core/app-shell/workspace-shell';
import { createManualSource, sourceKeys } from './api';

const schema = z.object({ name: z.string().trim().min(1).max(200) });
type Values = z.infer<typeof schema>;

export function SourceForm({ onSaved }: { onSaved: () => void }) {
  const { csrfToken } = useWorkspaceSession();
  const queryClient = useQueryClient();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name: '' } });
  const create = useMutation({ mutationFn: (values: Values) => createManualSource(values.name, csrfToken), onSuccess: () => { queryClient.invalidateQueries({ queryKey: sourceKeys.all }); onSaved(); } });
  return <form className="form" onSubmit={form.handleSubmit((values) => create.mutate(values))}>
    <div className="field"><Label htmlFor="source-name">Name</Label><Input id="source-name" autoFocus maxLength={200} {...form.register('name')} />{form.formState.errors.name && <span className="error">Enter a source name.</span>}</div>
    <p className="muted">A manual source groups notes you enter yourself.</p>
    {create.error && <p className="error" role="alert">{create.error instanceof ApiError ? create.error.message : 'Could not create source.'}</p>}
    <div className="form-actions"><Button type="submit" disabled={create.isPending}>Save source</Button><Button type="button" className="secondary" onClick={onSaved}>Cancel</Button></div>
  </form>;
}
