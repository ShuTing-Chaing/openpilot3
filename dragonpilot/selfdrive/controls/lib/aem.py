"""
Copyright (c) 2025, Rick Lan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, and/or sublicense,
for non-commercial purposes only, subject to the following conditions:

- The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.
- Commercial use (e.g. use in a product, service, or activity intended to
  generate revenue) is prohibited without explicit written permission from
  the copyright holder.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

# Adaptive Experimental Mode (AEM) picks the longitudinal mode from the model's
# throttle intent (the predicted gas-press probability). experimentalMode sets the
# default; the throttle intent only ever diverts away from it:
#   * blended-first (experimental on):  use ACC when the model clearly wants throttle.
#   * acc-first    (experimental off):  use BLENDED when the model clearly eases off.
# The asymmetric thresholds leave a 0.4-0.6 deadband where each mode holds its default.
THROTTLE_ACC_PROB     = 0.6  # gasPressProb >= this -> model wants throttle -> ACC
THROTTLE_BLENDED_PROB = 0.4  # gasPressProb <= this -> model easing off     -> BLENDED

# Blending factor for smooth mode transitions.
# At 20 Hz, 40 frames ≈ 2 seconds to fully blend.
BLEND_RAMP_FRAMES = 40


class AEM:
  def __init__(self):
    self._throttle_prob = 1.0
    self._blend = 0.0            # 0 = full blended, 1 = full acc
    self._prev_mode = 'blended'

  def update_states(self, model_msg, radar_msg, v_ego):
    # Probability the model wants to be on throttle (same signal the planner uses
    # for allow_throttle). High -> accelerate/cruise; low -> coast/slow.
    probs = model_msg.meta.disengagePredictions.gasPressProbs
    self._throttle_prob = probs[1] if len(probs) > 1 else 1.0

  def get_mode(self, mode):
    target = 'acc' if self._throttle_prob >= THROTTLE_ACC_PROB else 'blended'
    if mode != 'blended':
      # acc-first mode logic: swap when easing off
      target = 'blended' if self._throttle_prob <= THROTTLE_BLENDED_PROB else 'acc'

    # Ramp blend factor toward target
    if target == 'acc':
      self._blend = min(self._blend + 1.0 / BLEND_RAMP_FRAMES, 1.0)
    else:
      self._blend = max(self._blend - 1.0 / BLEND_RAMP_FRAMES, 0.0)

    return self._blend, target
