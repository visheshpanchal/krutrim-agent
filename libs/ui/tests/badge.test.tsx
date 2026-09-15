import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Badge } from '../src/lib/badge';

describe('Badge', () => {
  it('renders its children', () => {
    render(<Badge>Draft</Badge>);
    expect(screen.getByText('Draft').textContent).toBe('Draft');
  });

  it('applies the default variant classes when none is given', () => {
    render(<Badge>Default</Badge>);
    expect(screen.getByText('Default').className).toContain('bg-secondary');
  });

  it('switches variant classes when a variant is given', () => {
    render(<Badge variant="destructive">Failed</Badge>);
    const el = screen.getByText('Failed');
    expect(el.className).toContain('bg-destructive/10');
    expect(el.className).not.toContain('bg-secondary');
  });

  it('merges a caller-supplied className without dropping variant classes', () => {
    render(<Badge className="ml-2">Spaced</Badge>);
    expect(screen.getByText('Spaced').className).toContain('ml-2');
  });
});
