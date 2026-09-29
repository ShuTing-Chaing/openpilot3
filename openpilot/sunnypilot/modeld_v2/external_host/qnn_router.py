"""Time contracts for model candidates; never scales stale learned actions."""
from types import SimpleNamespace
import math


def action_context(output, context, now, tolerance, *, retime_plan=True):
  """Return a context aligned to this tick, or reject an immutable action head.

  Plan-based models expose a time-indexed trajectory that the existing action
  parser can sample. A learned scalar action was computed for its input action_t
  and must retain that target; changing action_t after inference cannot fix it.
  """
  capture = context['meta_main'].timestamp_eof / 1e9
  age = now - capture
  aligned = dict(context)
  target = {axis: now + context[f'{axis}_delay'] + .025 for axis in ('lat', 'long')}
  actual = {axis: capture + context[f'{axis}_action_t'] for axis in ('lat', 'long')}
  actuation_target = {axis: target[axis] - context.get(f'{axis}_smooth_seconds', 0.) for axis in target}
  for axis in target:
    immutable = not retime_plan or 'action' in output or (axis == 'lat' and 'desired_curvature' in output)
    if immutable:
      error = abs(actual[axis] - target[axis])
      if error <= tolerance:
        continue
      return None, {'reason': 'action_target_window', 'target_error_ms': error * 1000,
                    'predicted_target': actual, 'required_target': target, 'actuation_target': actuation_target}
    else:
      # This changes only existing trajectory sampling, never the recurrent graph.
      aligned[f'{axis}_action_t'] = age + context[f'{axis}_delay'] + .025
      actual[axis] = target[axis]
  return aligned, {'reason': '', 'predicted_target': actual, 'required_target': target,
                   'actuation_target': actuation_target,
                   'target_error_ms': max(abs(actual[axis] - target[axis]) for axis in target) * 1000}


def candidate_action(model, output, context):
  previous = SimpleNamespace(desiredAcceleration=context['prev_acceleration'], desiredCurvature=context['prev_curvature'])
  action = model.get_action_from_model(output, previous, context['lat_action_t'], context['long_action_t'], context['v_ego'])
  if not all(math.isfinite(float(value)) for value in (action.desiredAcceleration, action.desiredCurvature)):
    raise ValueError('Candidate action is not finite')
  return action


def compatible_actions(remote, local, v_ego, maximum_accel_difference, maximum_lateral_difference):
  """Conservative promotion guard, expressed in common physical units."""
  if bool(remote.shouldStop) != bool(local.shouldStop):
    return False, 'stop_disagreement'
  ra, la = float(remote.desiredAcceleration), float(local.desiredAcceleration)
  if (ra > .2 and la < -.5) or (la > .2 and ra < -.5):
    return False, 'braking_disagreement'
  if abs(ra - la) > maximum_accel_difference:
    return False, 'acceleration_disagreement'
  speed_squared = max(1., v_ego) ** 2
  rl, ll = remote.desiredCurvature * speed_squared, local.desiredCurvature * speed_squared
  if rl * ll < 0 and min(abs(rl), abs(ll)) > .4:
    return False, 'steering_direction_disagreement'
  if abs(rl - ll) > maximum_lateral_difference:
    return False, 'lateral_acceleration_disagreement'
  return True, ''
