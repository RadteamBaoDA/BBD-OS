'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { modules } from '@/core/module-registry';

function isEditing(target: EventTarget | null) {
  return target instanceof HTMLElement && Boolean(target.closest('input, textarea, select, [contenteditable], [role="textbox"]'));
}

export function CommandPalette() {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const actions = modules.filter((module) => module.enabled && module.label.toLocaleLowerCase().includes(filter.toLocaleLowerCase()));

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.isComposing) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen((value) => !value);
      } else if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !isEditing(event.target) && !dialogRef.current?.open) {
        const searchField = document.querySelector<HTMLInputElement>('[data-search-query]');
        if (searchField) { event.preventDefault(); searchField.focus(); }
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) { dialog.showModal(); inputRef.current?.focus(); }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return <><Button type="button" className="secondary" onClick={() => setOpen(true)} aria-keyshortcuts="Control+K Meta+K">Commands <span className="muted">⌘K</span></Button>
    <dialog ref={dialogRef} className="command-dialog" aria-label="Workspace commands" onClose={() => { setOpen(false); setFilter(''); }}>
      <div className="section-heading"><h2>Go to</h2><Button type="button" className="secondary" onClick={() => setOpen(false)}>Close</Button></div>
      <label className="label" htmlFor="command-filter">Filter actions</label><input ref={inputRef} id="command-filter" className="input" value={filter} onChange={(event) => setFilter(event.target.value)} />
      <ul className="command-actions">{actions.map((action) => <li key={action.id}><button type="button" className="text-button" onClick={() => { setOpen(false); router.push(action.href); }}>{action.label}</button></li>)}</ul>
      {actions.length === 0 && <p className="muted">No matching actions.</p>}
    </dialog>
  </>;
}
