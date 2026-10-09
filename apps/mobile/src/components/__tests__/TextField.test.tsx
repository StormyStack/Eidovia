import { fireEvent, render, screen } from '@testing-library/react-native';

import { TextField } from '../TextField';

it('shows the hint until there is an error, then the error replaces it', async () => {
  const { rerender } = await render(<TextField testID="f" label="Email" hint="We never share it." />);
  expect(screen.getByText('We never share it.')).toBeOnTheScreen();

  await rerender(<TextField testID="f" label="Email" hint="We never share it." error="Enter a valid email address." />);
  expect(screen.getByTestId('f-error')).toHaveTextContent('Enter a valid email address.');
  expect(screen.queryByText('We never share it.')).not.toBeOnTheScreen();
});

it('forwards focus and blur to the caller', async () => {
  const onFocus = jest.fn();
  const onBlur = jest.fn();
  await render(<TextField testID="f" label="Username" onFocus={onFocus} onBlur={onBlur} />);

  await fireEvent(screen.getByTestId('f'), 'focus');
  await fireEvent(screen.getByTestId('f'), 'blur');

  expect(onFocus).toHaveBeenCalledTimes(1);
  expect(onBlur).toHaveBeenCalledTimes(1);
});

it('is labelled for screen readers and only password fields get a toggle', async () => {
  await render(<TextField testID="f" label="Username" />);
  expect(screen.getByLabelText('Username')).toBeOnTheScreen();
  expect(screen.queryByRole('button', { name: 'Show password' })).not.toBeOnTheScreen();
});
