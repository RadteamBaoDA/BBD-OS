# Open-source inventory

| Package | Locked version | License | Use |
| --- | --- | --- | --- |
| [Authlib](https://github.com/authlib/authlib) | 1.8.0 | BSD-3-Clause | Server-side OpenID Connect discovery, authorization-code + PKCE flow, ID-token/JWKS validation for Google sign-in. |
| [itsdangerous](https://github.com/pallets/itsdangerous) | 2.2.0 | BSD-3-Clause | Required by Starlette `SessionMiddleware` for signed session-cookie support. |
| [Radix UI](https://github.com/radix-ui/primitives) | 1.6.7 | MIT | Primitives used by the account DropdownMenu and Dialog. |
| [HTTPX](https://github.com/encode/httpx) | 0.28.1 | BSD-3-Clause | OpenAI SDK HTTP transport with DNS result CIDR approval, numeric-IP pinning, and proxy/redirect denial at the OmniRoute boundary. |
| [cn](https://github.com/shadcn-ui/cn) | 0.4.0 | MIT | Tailwind-aware class merging in the locally owned shadcn component source. |
| [Lucide React](https://github.com/lucide-icons/lucide) | 1.49.0 | ISC | Close icon used by the generated Dialog component. |

The shadcn components are repository-owned source in `apps/web/src/components/ui/dialog.tsx`, `apps/web/src/components/ui/dropdown-menu.tsx`, `apps/web/src/components/ui/select.tsx`, and `apps/web/src/components/ui/checkbox.tsx`; `apps/web/components.json` records their New York style and Radix family. Install frontend dependencies with `npm ci` and backend dependencies with `uv sync`; versions are recorded in `package-lock.json` and `uv.lock`.

Google sign-in requests only `openid`, `email`, and `profile`; it does not grant Gmail access.
