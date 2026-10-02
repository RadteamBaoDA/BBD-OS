import type { ButtonHTMLAttributes } from 'react';

/** Renders the button UI wrapper and forwards its typed props to the underlying control. */
export function Button({ className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`button ${className}`} {...props} />;
}
