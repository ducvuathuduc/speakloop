// Shared primitives. Every interactive element is >= 48x48 and carries an accessible name.
import { STATUS, ringDash } from "./model.js";

const paths = {
  mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" /></>,
  stop: <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none" />,
  play: <path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none" />,
  pause: <><rect x="7" y="5.5" width="3.5" height="13" rx="1" fill="currentColor" stroke="none" /><rect x="13.5" y="5.5" width="3.5" height="13" rx="1" fill="currentColor" stroke="none" /></>,
  speaker: <><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" /><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" /></>,
  expand: <path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7" />,
  back: <path d="M15 5l-7 7 7 7" />,
  forward: <path d="M9 5l7 7-7 7" />,
  ear: <path d="M7 9a5 5 0 0 1 10 0c0 3-3 4-3 7a3 3 0 0 1-5.5 1.5M10 9.5a2 2 0 0 1 4 0" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  deletion: <><circle cx="12" cy="12" r="6.5" /><path d="M6 18L18 6" /></>,
  substitution: <path d="M5 9.5c2.3-2 4.7-2 7 0s4.7 2 7 0M5 15c2.3-2 4.7-2 7 0s4.7 2 7 0" />,
  insertion: <path d="M12 5.5v13M5.5 12h13" />,
  up: <path d="M12 18V6M6.5 11.5L12 6l5.5 5.5" />,
  down: <path d="M12 6v12M6.5 12.5L12 18l5.5-5.5" />,
  calendar: <><rect x="4" y="5.5" width="16" height="14" rx="2" /><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" /></>,
  info: <><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5.5M12 7.6v.2" /></>,
};

export function Icon({ name, size = 24, label, class: cls = "" }) {
  return (
    <svg class={`icon ${cls}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role={label ? "img" : undefined}
      aria-label={label} aria-hidden={label ? undefined : "true"} focusable="false">
      {paths[name]}
    </svg>
  );
}

/** Status is never colour alone: symbol + colour + accessible label. */
export function StatusMark({ type = "ok", size = 16 }) {
  const s = STATUS[type] || STATUS.ok;
  return <span class={`status status-${type}`} title={s.label}><Icon name={type === "ok" ? "check" : type} size={size} label={s.label} /></span>;
}

export function Brand() {
  return (
    <span class="brand" aria-label="SpeakLoop">
      <svg class="brand-mark" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <rect width="24" height="24" rx="6" class="brand-tile" />
        <path d="M7.2 18.2L10.4 5.8M13.6 18.2L16.8 5.8" class="brand-slash" />
      </svg>
      <span class="brand-word">SpeakLoop</span>
    </span>
  );
}

export function Button({ kind = "secondary", icon, iconEnd, children, onClick, label, disabled, pressed, class: cls = "" }) {
  return (
    <button type="button" class={`btn btn-${kind} ${children ? "" : "btn-icon"} ${cls}`} onClick={onClick}
      aria-label={label} disabled={disabled} aria-pressed={pressed}>
      {icon && <Icon name={icon} size={20} />}
      {children && <span>{children}</span>}
      {iconEnd && <Icon name={iconEnd} size={18} />}
    </button>
  );
}

export function Shell({ title, right, children, class: cls = "", label }) {
  return (
    <article class={`card ${cls}`} aria-label={label || title || "SpeakLoop"}>
      <header class="card-head">
        <Brand />
        {title && <span class="card-title">{title}</span>}
        <span class="spacer" />
        {right}
      </header>
      {children}
    </article>
  );
}

export function Ring({ value, size = 136, stroke = 14, label }) {
  const r = (size - stroke) / 2 - 1; // 1px inset: no edge clipping under fractional device zoom
  const { c, offset } = ringDash(value, r);
  return (
    <svg class="ring" overflow="visible" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label}>
      <circle class="ring-track" cx={size / 2} cy={size / 2} r={r} stroke-width={stroke} fill="none" />
      <circle class="ring-value" cx={size / 2} cy={size / 2} r={r} stroke-width={stroke} fill="none"
        stroke-dasharray={c} stroke-dashoffset={offset} stroke-linecap="round" transform={`rotate(-90 ${size / 2} ${size / 2})`} />
    </svg>
  );
}

export function Segmented({ options, value, onChange, label }) {
  return (
    <div class="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button type="button" role="radio" aria-checked={o.value === value} class={o.value === value ? "on" : ""}
          onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

export function Legend() {
  return (
    <ul class="legend" aria-label="Legend">
      <li><StatusMark type="ok" size={14} /> Heard</li>
      <li><StatusMark type="substitution" size={14} /> Changed</li>
      <li><StatusMark type="deletion" size={14} /> Missing</li>
    </ul>
  );
}
