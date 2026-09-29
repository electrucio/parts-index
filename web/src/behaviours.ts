/**
 * The words for what a model's author declares about it, by the ids `models claims` publishes
 * (src/parts_index/models/behaviours.py). Short, because they sit in a table cell.
 */
export const CLAIM_LABEL: Record<string, string> = {
  'offset': 'offset',
  'bias-current': 'bias current',
  'open-loop-gain': 'open-loop gain',
  'cmrr': 'CMRR',
  'input-range': 'input range',
  'input-impedance': 'input impedance',
  'gain-phase': 'gain and phase',
  'bandwidth': 'bandwidth',
  'settling': 'settling',
  'step-response': 'step response',
  'slew': 'slew rate',
  'noise': 'noise',
  'noise-1f': '1/f noise',
  'current-noise': 'current noise',
  'distortion': 'distortion',
  'temperature': 'temperature',
  'psrr': 'PSRR',
  'supply-current': 'supply current',
  'output-swing': 'output swing',
  'output-current': 'output current',
  'current-limit': 'current limit',
  'overload-recovery': 'overload recovery',
  'phase-reversal': 'phase reversal',
  'output-impedance': 'output impedance',
}

/** Qualifications an author attaches to the whole model. */
export const LIMIT_LABEL: Record<string, string> = {
  'vos-static': 'offset fixed',
  'ib-static': 'bias current fixed',
  '25c-only': '25 °C only',
  'typical-only': 'typical values only',
  'supply-fixed': 'one supply voltage',
}
