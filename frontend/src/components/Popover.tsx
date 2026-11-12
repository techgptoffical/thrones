import { useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  /** Renders the trigger; call toggle() from its onClick. */
  trigger: (toggle: () => void, open: boolean) => ReactNode;
  children: (close: () => void) => ReactNode;
  side?: "up" | "down";
  align?: "left" | "right";
  className?: string;
  onOpenChange?: (open: boolean) => void;
}

/** A small anchored menu that closes on outside click or Escape. */
export function Popover({ trigger, children, side = "down", align = "left", className = "", onOpenChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  const change = (next: boolean) => {
    setOpen(next);
    onOpenChange?.(next);
  };

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) change(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        change(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <span className="pop-anchor" ref={ref}>
      {trigger(() => change(!open), open)}
      {open && (
        <div className={`menu ${side} ${align} ${className}`} role="menu">
          {children(() => change(false))}
        </div>
      )}
    </span>
  );
}
