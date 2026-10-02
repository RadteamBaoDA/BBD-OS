import { redirect } from 'next/navigation';

/** Redirects the legacy models route to its current AI settings owner. */
export default function ModelsPage() { redirect('/settings/ai'); }
