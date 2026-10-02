import type { InputHTMLAttributes } from 'react';

/** Renders the input UI wrapper and forwards its typed props to the underlying control. */
export function Input({ className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`input ${className}`} {...props} />;
}
