import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TagChip } from '../components/TagChip';

describe('TagChip', () => {
  it('renders name with color background', () => {
    render(<TagChip id={1} name="财务" color="#FF540E" mode="readonly" />);
    const chip = screen.getByText('财务');
    expect(chip).toBeInTheDocument();
    expect(chip.style.backgroundColor).toBe('rgb(255, 84, 14)');
  });

  it('renders remove button in removable mode', () => {
    const onRemove = vi.fn();
    render(
      <TagChip id={1} name="财务" color="#FF540E" mode="removable" onRemove={onRemove} />
    );
    const removeBtn = screen.getByRole('button', { name: /删除/ });
    fireEvent.click(removeBtn);
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it('does not show remove in readonly mode', () => {
    render(<TagChip id={1} name="财务" color="#FF540E" mode="readonly" />);
    expect(screen.queryByRole('button', { name: /删除/ })).not.toBeInTheDocument();
  });
});
