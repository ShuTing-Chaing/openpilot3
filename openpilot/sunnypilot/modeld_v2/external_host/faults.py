"""Closed fault taxonomy shared by the router and the OPIF IPC boundary."""
from .wire import HostError
import errno


class TransportUnavailable(HostError):
  """No verified terminal response; reconnect and requalify a new history."""


class HistoryResetRequired(HostError):
  """An input was not executed on the required sequence/cadence."""


class TransientBackpressure(HostError):
  """Local admission is full; drop this frame without resetting the transport."""


class FatalModelFault(HostError):
  """Model identity, schema, output or protocol integrity was not valid."""


FAULT_TYPES = {'transport_unavailable': TransportUnavailable,
               'history_reset_required': HistoryResetRequired,
               'fatal_model_fault': FatalModelFault}


def classify(error):
  if isinstance(error, (TransportUnavailable, HistoryResetRequired, FatalModelFault)):
    return error
  if isinstance(error, (ConnectionError, EOFError, TimeoutError)):
    return TransportUnavailable(str(error))
  if isinstance(error, OSError) and error.errno in {
      errno.ECONNREFUSED, errno.ECONNRESET, errno.ECONNABORTED, errno.ENETDOWN,
      errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ETIMEDOUT, errno.EPIPE}:
    return TransportUnavailable(str(error))
  return FatalModelFault(str(error))


def fault_kind(error):
  fault = classify(error)
  return next(name for name, kind in FAULT_TYPES.items() if isinstance(fault, kind))


def from_wire(kind, message):
  # Unknown/missing classifications fail closed; no error-string heuristics.
  return FAULT_TYPES.get(kind, FatalModelFault)(str(message))
