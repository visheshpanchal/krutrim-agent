import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Button } from '../src/lib/button';

describe('Button', () => {
  it('renders its children and responds to clicks', () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Send</Button>);
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('is disabled when the disabled prop is set, and does not fire onClick', () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Send
      </Button>,
    );
    const button = screen.getByRole('button', { name: 'Send' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('forwards a ref to the underlying <button> element', () => {
    const ref = { current: null as HTMLButtonElement | null };
    render(<Button ref={ref}>Send</Button>);
    expect(ref.current).toBeInstanceOf(HTMLButtonElement);
  });
});
