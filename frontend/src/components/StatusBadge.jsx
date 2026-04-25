import { Badge } from './ui/Badge'

const STATE_MAP = {
  RUNNING:  { label: 'Printing',  variant: 'success' },
  PAUSE:    { label: 'Paused',    variant: 'warning' },
  FINISH:   { label: 'Finished',  variant: 'info' },
  FAILED:   { label: 'Failed',    variant: 'danger' },
  IDLE:     { label: 'Idle',      variant: 'muted' },
  OFFLINE:  { label: 'Offline',   variant: 'danger' },
  PREPARE:  { label: 'Preparing', variant: 'warning' },
  SLICING:  { label: 'Slicing',   variant: 'warning' },
}

export function StatusBadge({ state }) {
  const { label, variant } = STATE_MAP[state] ?? { label: state, variant: 'default' }
  return <Badge variant={variant}>{label}</Badge>
}
