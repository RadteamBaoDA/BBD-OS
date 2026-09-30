# Open-source inventory

| Package | Locked version | License | Use |
| --- | --- | --- | --- |
| [Authlib](https://github.com/authlib/authlib) | 1.8.0 | BSD-3-Clause | Server-side OpenID Connect discovery, authorization-code + PKCE flow, ID-token/JWKS validation for Google sign-in. |
| [itsdangerous](https://github.com/pallets/itsdangerous) | 2.2.0 | BSD-3-Clause | Required by Starlette `SessionMiddleware` for signed session-cookie support. |
| [Radix UI](https://github.com/radix-ui/primitives) | 1.6.7 | MIT | Primitives used by the account DropdownMenu and Dialog. |
| [cn](https://github.com/shadcn-ui/cn) | 0.4.0 | MIT | Tailwind-aware class merging in the locally owned shadcn component source. |
| [Lucide React](https://github.com/lucide-icons/lucide) | 1.49.0 | ISC | Close icon used by the generated Dialog component. |

The shadcn components are repository-owned source in `apps/web/src/components/ui/dialog.tsx` and `apps/web/src/components/ui/dropdown-menu.tsx`; `apps/web/components.json` records their New York style and Radix family. Install frontend dependencies with `npm ci` and backend dependencies with `uv sync`; versions are recorded in `package-lock.json` and `uv.lock`.

Google sign-in requests only `openid`, `email`, and `profile`; it does not grant Gmail access.
