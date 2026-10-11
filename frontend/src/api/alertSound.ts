export function playIncidentBuzzer(enabled: boolean) {
  if (!enabled) return
  try {
    const context = new AudioContext()
    const oscillator = context.createOscillator()
    const gain = context.createGain()
    const start = context.currentTime
    oscillator.type = 'square'
    oscillator.connect(gain)
    gain.connect(context.destination)
    for (let beat = 0; beat < 4; beat++) {
      const at = start + beat * 0.24
      oscillator.frequency.setValueAtTime(920, at)
      oscillator.frequency.setValueAtTime(690, at + 0.11)
      gain.gain.setValueAtTime(0.0001, at)
      gain.gain.linearRampToValueAtTime(0.075, at + 0.015)
      gain.gain.setValueAtTime(0.075, at + 0.14)
      gain.gain.setValueAtTime(0.0001, at + 0.17)
    }
    oscillator.start(start)
    oscillator.stop(start + 1.05)
    oscillator.onended = () => { void context.close() }
  } catch {
    // Audio can be blocked until the operator interacts with the page.
  }
}

export function unlockAudioAlerts() {
  try {
    const context = new AudioContext()
    void context.resume().finally(() => context.close())
  } catch {
    // Unsupported audio remains optional; the visual alert is still shown.
  }
}