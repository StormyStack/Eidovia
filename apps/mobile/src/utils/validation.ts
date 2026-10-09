/**
 * Client-side form validation. Rules mirror the Gateway (apps/gateway/app/schemas.py,
 * docs/api-auth-home.md) so users see problems before a round trip; the server
 * remains the authority and its field errors are shown too.
 */

export const USERNAME_MIN = 3;
export const USERNAME_MAX = 32;
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX_BYTES = 72; // bcrypt limit
export const EMAIL_MAX = 254;

const USERNAME_PATTERN = /^[A-Za-z0-9_.-]+$/;
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export type FieldErrors<K extends string> = Partial<Record<K, string>>;

export interface LoginValues {
  username: string;
  password: string;
}

export interface SignUpValues {
  username: string;
  email: string;
  password: string;
  confirmPassword: string;
}

/** UTF-8 byte length (bcrypt counts bytes, not characters). */
export function utf8Length(value: string): number {
  let bytes = 0;
  for (const char of value) {
    const code = char.codePointAt(0) ?? 0;
    bytes += code <= 0x7f ? 1 : code <= 0x7ff ? 2 : code <= 0xffff ? 3 : 4;
  }
  return bytes;
}

export function validateUsername(raw: string): string | undefined {
  const value = raw.trim();
  if (!value) return 'Enter a username.';
  if (value.length < USERNAME_MIN || value.length > USERNAME_MAX) {
    return `Username must be ${USERNAME_MIN} to ${USERNAME_MAX} characters.`;
  }
  if (!USERNAME_PATTERN.test(value)) {
    return 'Use only letters, numbers, underscores (_), dots (.) and hyphens (-).';
  }
  return undefined;
}

export function validateEmail(raw: string): string | undefined {
  const value = raw.trim();
  if (!value) return 'Enter your email address.';
  if (value.length > EMAIL_MAX || !EMAIL_PATTERN.test(value)) return 'Enter a valid email address.';
  return undefined;
}

export function validateNewPassword(value: string): string | undefined {
  if (!value) return 'Enter a password.';
  if (value.length < PASSWORD_MIN) return `Password must be at least ${PASSWORD_MIN} characters.`;
  if (utf8Length(value) > PASSWORD_MAX_BYTES) return `Password must be at most ${PASSWORD_MAX_BYTES} characters.`;
  return undefined;
}

export function validateLogin(values: LoginValues): FieldErrors<keyof LoginValues> {
  const errors: FieldErrors<keyof LoginValues> = {};
  if (!values.username.trim()) errors.username = 'Enter your username.';
  if (!values.password) errors.password = 'Enter your password.';
  return errors;
}

export function validateSignUp(values: SignUpValues): FieldErrors<keyof SignUpValues> {
  const errors: FieldErrors<keyof SignUpValues> = {};
  const username = validateUsername(values.username);
  const email = validateEmail(values.email);
  const password = validateNewPassword(values.password);
  if (username) errors.username = username;
  if (email) errors.email = email;
  if (password) errors.password = password;
  if (!values.confirmPassword) errors.confirmPassword = 'Re-enter your password.';
  else if (values.confirmPassword !== values.password) errors.confirmPassword = 'Passwords do not match.';
  return errors;
}

export const hasErrors = (errors: Record<string, string | undefined>): boolean =>
  Object.values(errors).some(Boolean);
