import { redirect } from 'next/navigation';

/** Redirects the legacy privacy route to the consolidated AI settings page. */
export default function PrivacyPage() { redirect('/settings/ai'); }
