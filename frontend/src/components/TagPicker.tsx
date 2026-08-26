import { useState } from 'react';
import { TagChip } from './TagChip';

interface TagPickerProps {
  availableTags: Array<{ id: number; name: string; color: string }>;
  initialSelectedIds?: number[];
  onConfirm: (selectedIds: number[]) => void;
  onCancel: () => void;
}

export function TagPicker({
  availableTags,
  initialSelectedIds = [],
  onConfirm,
  onCancel,
}: TagPickerProps) {
  const [selected, setSelected] = useState<Set<number>>(new Set(initialSelectedIds));

  const toggle = (id: number) => {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="modal-backdrop" role="dialog">
      <div className="modal">
        <h3>选择标签</h3>
        <div className="tag-picker-grid">
          {availableTags.map((t) => (
            <TagChip
              key={t.id}
              id={t.id}
              name={t.name}
              color={t.color}
              mode="editable"
              selected={selected.has(t.id)}
              onToggle={toggle}
            />
          ))}
        </div>
        <div className="modal-actions">
          <button className="btn-secondary" onClick={onCancel}>取消</button>
          <button
            className="btn-primary"
            onClick={() => onConfirm(Array.from(selected))}
            disabled={selected.size === 0}
          >
            确认 ({selected.size})
          </button>
        </div>
      </div>
    </div>
  );
}
