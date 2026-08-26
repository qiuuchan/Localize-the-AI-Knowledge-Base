interface TagChipProps {
  id: number;
  name: string;
  color: string;
  mode?: 'readonly' | 'editable' | 'removable';
  selected?: boolean;
  onRemove?: (id: number) => void;
  onToggle?: (id: number) => void;
}

export function TagChip({
  id,
  name,
  color,
  mode = 'readonly',
  selected = false,
  onRemove,
  onToggle,
}: TagChipProps) {
  const handleClick = () => {
    if (mode === 'editable' && onToggle) onToggle(id);
  };

  return (
    <span
      className={`tag-chip ${mode} ${selected ? 'selected' : ''}`}
      style={{ backgroundColor: color }}
      onClick={handleClick}
      data-testid={`tag-chip-${id}`}
    >
      {name}
      {mode === 'removable' && (
        <button
          className="tag-chip-remove"
          onClick={(e) => {
            e.stopPropagation();
            onRemove?.(id);
          }}
          aria-label={`删除标签 ${name}`}
        >
          ×
        </button>
      )}
    </span>
  );
}
