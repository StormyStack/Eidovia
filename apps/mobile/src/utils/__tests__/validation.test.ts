import { hasErrors, utf8Length, validateEmail, validateLogin, validateNewPassword, validateSignUp, validateUsername } from '../validation';

describe('validateUsername (mirrors the Gateway)', () => {
  it.each(['abc', 'Shanto_23', 'a.b-c', 'x'.repeat(32), '  trimmed  '])('accepts %s', (value) => {
    expect(validateUsername(value)).toBeUndefined();
  });
  it.each([
    ['', 'Enter a username.'],
    ['   ', 'Enter a username.'],
    ['ab', 'Username must be 3 to 32 characters.'],
    ['x'.repeat(33), 'Username must be 3 to 32 characters.'],
    ['bad name', 'Use only letters'],
    ['émile', 'Use only letters'],
  ])('rejects %j', (value, message) => {
    expect(validateUsername(value)).toContain(message);
  });
});

describe('validateEmail', () => {
  it.each(['a@b.co', ' Shanto@Example.com '])('accepts %s', (value) => expect(validateEmail(value)).toBeUndefined());
  it.each(['', 'nope', 'a@b', 'a b@c.d', `${'x'.repeat(250)}@b.co`])('rejects %j', (value) => expect(validateEmail(value)).toBeDefined());
});

describe('validateNewPassword (bcrypt limits)', () => {
  it('requires at least 8 characters', () => {
    expect(validateNewPassword('')).toBe('Enter a password.');
    expect(validateNewPassword('1234567')).toContain('at least 8');
    expect(validateNewPassword('12345678')).toBeUndefined();
  });
  it('counts bytes, not characters, against the 72-byte limit', () => {
    expect(validateNewPassword('a'.repeat(72))).toBeUndefined();
    expect(validateNewPassword('a'.repeat(73))).toContain('at most 72');
    expect(validateNewPassword('é'.repeat(37))).toContain('at most 72'); // 74 bytes
  });
  it('utf8Length handles 1-4 byte characters', () => {
    expect(utf8Length('a')).toBe(1);
    expect(utf8Length('é')).toBe(2);
    expect(utf8Length('অ')).toBe(3);
    expect(utf8Length('😀')).toBe(4);
  });
});

describe('form validators', () => {
  it('validateLogin requires both fields', () => {
    expect(validateLogin({ username: ' ', password: '' })).toEqual({ username: 'Enter your username.', password: 'Enter your password.' });
    expect(hasErrors(validateLogin({ username: 'a', password: 'b' }))).toBe(false);
  });

  it('validateSignUp checks confirm password', () => {
    const base = { username: 'shanto', email: 'a@b.co', password: 'Correct-Horse-9' };
    expect(validateSignUp({ ...base, confirmPassword: '' }).confirmPassword).toBe('Re-enter your password.');
    expect(validateSignUp({ ...base, confirmPassword: 'other' }).confirmPassword).toBe('Passwords do not match.');
    expect(hasErrors(validateSignUp({ ...base, confirmPassword: base.password }))).toBe(false);
  });
});
