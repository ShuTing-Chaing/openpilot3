#!/usr/bin/env python3
"""Phone navigation receiver: LAN discovery, WebSocket JSON, official cereal output."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import queue
import socket
import struct
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps
from msgq.visionipc import VisionIpcServer

import openpilot.cereal.messaging as messaging
from openpilot.cereal.visionipc import VisionStreamType
from openpilot.common.params import Params
from openpilot.selfdrive.navigation.helpers import latest_gps_source

LOGGER = logging.getLogger("phone_navi")
DISCOVERY_PORT = 7705
WEBSOCKET_PORT = 7714
MAP_STREAM_NAME = "phone_navi"
MAP_WIDTH = 384
MAP_HEIGHT = 512
MAP_JPEG_MAX_BYTES = 4 * 1024 * 1024
SERVICE = "mrone-phone-navi"
STATE_PATH = Path("/data/phone_navi_state.json")
MAX_FRAME_BYTES = 16 * 1024 * 1024
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _safe_json(data: bytes) -> dict[str, Any] | None:
  try:
    value = json.loads(data.decode("utf-8"))
    return value if isinstance(value, dict) else None
  except Exception:
    return None


def _recv_exact(conn: socket.socket, length: int) -> bytes:
  data = bytearray()
  while len(data) < length:
    chunk = conn.recv(length - len(data))
    if not chunk:
      raise ConnectionError("socket closed")
    data.extend(chunk)
  return bytes(data)


def _read_frame(conn: socket.socket) -> tuple[int, bytes]:
  header = _recv_exact(conn, 2)
  opcode = header[0] & 0x0F
  masked = bool(header[1] & 0x80)
  length = header[1] & 0x7F
  if length == 126:
    length = struct.unpack("!H", _recv_exact(conn, 2))[0]
  elif length == 127:
    length = struct.unpack("!Q", _recv_exact(conn, 8))[0]
  if length > MAX_FRAME_BYTES:
    raise ValueError("WebSocket frame too large")
  mask = _recv_exact(conn, 4) if masked else b""
  payload = _recv_exact(conn, length)
  if masked:
    payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
  return opcode, payload


def _send_frame(conn: socket.socket, opcode: int, payload: bytes) -> None:
  first = 0x80 | opcode
  length = len(payload)
  if length < 126:
    header = bytes((first, length))
  elif length <= 0xFFFF:
    header = bytes((first, 126)) + struct.pack("!H", length)
  else:
    header = bytes((first, 127)) + struct.pack("!Q", length)
  conn.sendall(header + payload)


def _send_json(conn: socket.socket, payload: dict[str, Any]) -> None:
  _send_frame(conn, 0x1, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


class MapStreamPublisher:
  """Decode phone JPEG map frames and expose RGB frames on VisionIPC."""

  def __init__(self):
    self.server = VisionIpcServer(MAP_STREAM_NAME)
    self.server.create_buffers_with_sizes(
      VisionStreamType.VISION_STREAM_MAP,
      4,
      MAP_WIDTH,
      MAP_HEIGHT,
      MAP_WIDTH * MAP_HEIGHT * 3,
      MAP_WIDTH * 3,
      0,
    )
    self.server.start_listener()
    self.frames: queue.Queue[bytes | None] = queue.Queue(maxsize=2)
    self.frame_id = 0
    threading.Thread(target=self._run, name="phone-map-stream", daemon=True).start()

  def submit(self, jpeg: bytes) -> None:
    if not jpeg or len(jpeg) > MAP_JPEG_MAX_BYTES:
      return
    try:
      self.frames.put_nowait(jpeg)
    except queue.Full:
      try:
        self.frames.get_nowait()
      except queue.Empty:
        pass
      try:
        self.frames.put_nowait(jpeg)
      except queue.Full:
        pass

  def _run(self) -> None:
    while True:
      jpeg = self.frames.get()
      if jpeg is None:
        return
      try:
        with Image.open(io.BytesIO(jpeg)) as source:
          image = ImageOps.fit(source.convert("RGB"), (MAP_WIDTH, MAP_HEIGHT), method=Image.Resampling.BILINEAR)
        rgb = np.asarray(image, dtype=np.uint8).reshape(-1)
        now = time.monotonic_ns()
        self.server.send(VisionStreamType.VISION_STREAM_MAP, rgb.tobytes(), self.frame_id, now, now)
        self.frame_id += 1
      except Exception:
        LOGGER.exception("phone map frame decode failed")


def _handshake(conn: socket.socket, request: bytes) -> str | None:
  lines = request.decode("latin-1", "replace").split("\r\n")
  if not lines or not lines[0].startswith("GET "):
    return None
  path = lines[0].split(" ", 2)[1]
  headers = {}
  for line in lines[1:]:
    if ":" in line:
      name, value = line.split(":", 1)
      headers[name.strip().lower()] = value.strip()
  key = headers.get("sec-websocket-key")
  if not key:
    return None
  accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
  response = (
    "HTTP/1.1 101 Switching Protocols\r\n"
    "Upgrade: websocket\r\n"
    "Connection: Upgrade\r\n"
    f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
  )
  conn.sendall(response.encode("ascii"))
  return path


class CerealPublisher:
  def __init__(self):
    self.pm = messaging.PubMaster(["navInstruction", "navRoute"])
    self.lock = threading.Lock()
    self.last_route: list[dict[str, float]] | None = None
    self.last_instruction: dict[str, Any] | None = None
    self.heartbeat_stop = threading.Event()
    threading.Thread(target=self._heartbeat, name="phone-nav-heartbeat", daemon=True).start()

  def publish_route(self, coordinates: list[dict[str, Any]]) -> None:
    cleaned = []
    for item in coordinates:
      try:
        cleaned.append({"longitude": float(item["longitude"]), "latitude": float(item["latitude"])})
      except (KeyError, TypeError, ValueError):
        continue
    if len(cleaned) < 2:
      raise ValueError("navRoute needs at least two coordinates")
    with self.lock:
      message = messaging.new_message("navRoute", valid=True)
      message.navRoute.coordinates = cleaned
      self.pm.send("navRoute", message)
      self.last_route = cleaned

  def publish_instruction(self, payload: dict[str, Any]) -> None:
    with self.lock:
      message = messaging.new_message("navInstruction", valid=True)
      instruction = message.navInstruction
      instruction.maneuverPrimaryText = str(payload.get("maneuverPrimaryText") or "")
      instruction.maneuverSecondaryText = str(payload.get("maneuverSecondaryText") or "")
      instruction.maneuverDistance = float(payload.get("maneuverDistance") or 0.0)
      instruction.maneuverType = str(payload.get("maneuverType") or "turn")
      instruction.maneuverModifier = str(payload.get("maneuverModifier") or "straight")
      instruction.distanceRemaining = float(payload.get("distanceRemaining") or 0.0)
      instruction.timeRemaining = float(payload.get("timeRemaining") or 0.0)
      instruction.timeRemainingTypical = float(payload.get("timeRemainingTypical") or instruction.timeRemaining)
      instruction.showFull = bool(payload.get("showFull", True))
      speed_limit = float(payload.get("speedLimit") if payload.get("speedLimit") is not None else -1.0)
      if speed_limit >= 0:
        instruction.speedLimit = speed_limit
      maneuvers = payload.get("allManeuvers") or []
      if isinstance(maneuvers, list):
        instruction.allManeuvers = [
          {
            "distance": float(item.get("distance") or 0.0),
            "type": str(item.get("type") or ""),
            "modifier": str(item.get("modifier") or ""),
          }
          for item in maneuvers if isinstance(item, dict)
        ]
      self.pm.send("navInstruction", message)
      self.last_instruction = payload

  def replay(self) -> None:
    if self.last_route is not None:
      self.publish_route(self.last_route)
    if self.last_instruction is not None:
      self.publish_instruction(self.last_instruction)

  def clear(self) -> None:
    with self.lock:
      route = messaging.new_message("navRoute", valid=True)
      route.navRoute.coordinates = []
      self.pm.send("navRoute", route)
      instruction = messaging.new_message("navInstruction", valid=False)
      self.pm.send("navInstruction", instruction)
      self.last_route = None
      self.last_instruction = None

  def _heartbeat(self) -> None:
    last_route_at = 0.0
    while not self.heartbeat_stop.is_set():
      try:
        if self.last_instruction is not None:
          self.publish_instruction(self.last_instruction)
        now = time.monotonic()
        if self.last_route is not None and now - last_route_at >= 5.0:
          self.publish_route(self.last_route)
          last_route_at = now
      except Exception:
        LOGGER.exception("phone navigation heartbeat failed")
      self.heartbeat_stop.wait(1.0)

  def resend_last(self) -> None:
    self.replay()


class PhoneNaviServer:
  def __init__(self):
    self.params = Params()
    self.device_id = str(self.params.get("DongleId") or "comma-device")
    self.hostname = socket.gethostname()
    self.publisher = CerealPublisher()
    self.map_publisher = MapStreamPublisher()
    self.stop_event = threading.Event()
    self.clients_lock = threading.Lock()
    self.clients: dict[socket.socket, threading.Lock] = {}
    self.last_location: dict[str, Any] | None = None
    self.state = self.load_state()
    Path("/data/phone_navi_active").touch()
    self.params.put_bool("NavigationEnabled", True, block=True)
    self.restore_state()
    threading.Thread(target=self.telemetry_loop, name="phone-nav-telemetry", daemon=True).start()

  def send_json(self, conn: socket.socket, payload: dict[str, Any]) -> None:
    with self.clients_lock:
      send_lock = self.clients.get(conn)
    if send_lock is None:
      return
    with send_lock:
      _send_json(conn, payload)

  def telemetry_loop(self) -> None:
    sm = messaging.SubMaster(["gpsLocation", "gpsLocationExternal"])
    while not self.stop_event.is_set():
      sm.update(200)
      source = latest_gps_source(sm)
      if source is None:
        continue
      gps = sm[source]
      location = {
        "type": "vehicleLocation",
        "latitude": float(gps.latitude),
        "longitude": float(gps.longitude),
        "bearingDeg": float(gps.bearingDeg),
        "speed": float(gps.speed),
        "horizontalAccuracy": float(gps.horizontalAccuracy),
        "satelliteCount": int(gps.satelliteCount),
        "source": source,
      }
      self.last_location = location
      with self.clients_lock:
        clients = list(self.clients.items())
      for conn, _ in clients:
        try:
          self.send_json(conn, location)
        except OSError:
          pass

  def discovery_loop(self) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", DISCOVERY_PORT))
    sock.settimeout(1.0)
    LOGGER.warning("phone_navi discovery listening on UDP %d", DISCOVERY_PORT)
    while not self.stop_event.is_set():
      try:
        data, address = sock.recvfrom(4096)
      except socket.timeout:
        continue
      payload = _safe_json(data)
      if not payload or payload.get("service") != SERVICE or payload.get("type") != "discover":
        continue
      probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      try:
        probe.connect(address)
        local_ip = probe.getsockname()[0]
      except OSError:
        local_ip = ""
      finally:
        probe.close()
      reply = {
        "service": SERVICE,
        "version": 1,
        "type": "device",
        "device_id": self.device_id,
        "name": self.hostname,
        "ip": local_ip,
        "ws_port": WEBSOCKET_PORT,
      }
      try:
        sock.sendto(json.dumps(reply, ensure_ascii=False).encode("utf-8"), address)
      except OSError:
        pass

  def load_state(self) -> dict[str, dict[str, Any] | None]:
    state: dict[str, dict[str, Any] | None] = {"destination": None, "route": None, "instruction": None}
    try:
      saved = json.loads(STATE_PATH.read_text(encoding="utf-8"))
      for key in state:
        if isinstance(saved.get(key), dict):
          state[key] = saved[key]
      legacy = saved.get("last_message")
      if isinstance(legacy, dict):
        legacy_type = legacy.get("type")
        if legacy_type == "destination" and state["destination"] is None:
          state["destination"] = legacy
        elif legacy_type == "navRoute" and state["route"] is None:
          state["route"] = legacy
        elif legacy_type == "navInstruction" and state["instruction"] is None:
          state["instruction"] = legacy
    except (OSError, ValueError, TypeError):
      pass
    return state

  def save_state(self, payload: dict[str, Any]) -> None:
    message_type = payload.get("type")
    if message_type == "destination":
      self.state["destination"] = payload
    elif message_type == "navRoute":
      self.state["route"] = payload
    elif message_type == "navInstruction":
      self.state["instruction"] = payload
    try:
      tmp = STATE_PATH.with_suffix(".tmp")
      data = {"updated_at": time.time(), **self.state}
      tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
      os.replace(tmp, STATE_PATH)
    except OSError:
      LOGGER.exception("failed to save phone navigation state")

  def clear_navigation(self) -> None:
    self.publisher.clear()
    self.state = {"destination": None, "route": None, "instruction": None}
    try:
      tmp = STATE_PATH.with_suffix(".tmp")
      data = {"updated_at": time.time(), **self.state}
      tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
      os.replace(tmp, STATE_PATH)
    except OSError:
      LOGGER.exception("failed to clear phone navigation state")
    self.params.remove("NavDestination")
    self.params.put_bool("NavigationEnabled", False, block=True)

  def restore_state(self) -> None:
    destination = self.state.get("destination")
    if isinstance(destination, dict):
      longitude = float(destination.get("longitude") or 0.0)
      latitude = float(destination.get("latitude") or 0.0)
      if longitude != 0.0 and latitude != 0.0:
        self.params.put("NavDestination", {
          "name": str(destination.get("name") or ""),
          "longitude": longitude,
          "latitude": latitude,
        }, block=True)
    route = self.state.get("route")
    if isinstance(route, dict) and isinstance(route.get("coordinates"), list):
      try:
        self.publisher.publish_route(route["coordinates"])
      except ValueError:
        pass
    instruction = self.state.get("instruction")
    if isinstance(instruction, dict):
      self.publisher.publish_instruction(instruction)

  def handle_client(self, conn: socket.socket, address: tuple[str, int]) -> None:
    try:
      conn.settimeout(10)
      request = bytearray()
      while b"\r\n\r\n" not in request and len(request) < 16384:
        chunk = conn.recv(4096)
        if not chunk:
          return
        request.extend(chunk)
      path = _handshake(conn, bytes(request))
      if path is None or not path.startswith("/api/phone-navi/v1"):
        return
      conn.settimeout(None)
      with self.clients_lock:
        self.clients[conn] = threading.Lock()
      LOGGER.warning("phone_navi client connected: %s", address)
      map_info = {"encoding": "jpeg", "width": MAP_WIDTH, "height": MAP_HEIGHT, "fps": 5}
      self.send_json(conn, {"type": "welcome", "protocol": 1, "device_id": self.device_id, "map": map_info})
      self.publisher.resend_last()
      if self.publisher.last_route is not None:
        self.send_json(conn, {"type": "navRouteAck", "count": len(self.publisher.last_route)})
      if self.publisher.last_instruction is not None:
        self.send_json(conn, {"type": "navInstructionAck"})
      if self.last_location is not None:
        self.send_json(conn, self.last_location)
      while not self.stop_event.is_set():
        opcode, data = _read_frame(conn)
        if opcode == 0x8:
          break
        if opcode == 0x9:
          _send_frame(conn, 0xA, data)
          continue
        if opcode == 0x2:
          self.map_publisher.submit(data)
          continue
        if opcode != 0x1:
          continue
        payload = _safe_json(data)
        if payload is None:
          continue
        message_type = str(payload.get("type") or "")
        self.save_state(payload)
        if message_type == "hello":
          self.send_json(conn, {"type": "helloAck", "protocol": 1, "map": map_info})
        elif message_type == "destination":
          destination = {
            "name": str(payload.get("name") or ""),
            "longitude": float(payload.get("longitude") or 0.0),
            "latitude": float(payload.get("latitude") or 0.0),
          }
          if destination["longitude"] != 0.0 and destination["latitude"] != 0.0:
            self.params.put("NavDestination", destination, block=True)
          self.params.put_bool("NavigationEnabled", True, block=True)
          self.send_json(conn, {"type": "destinationAck"})
        elif message_type == "navRoute":
          coordinates = payload.get("coordinates") or []
          self.publisher.publish_route(coordinates)
          self.send_json(conn, {"type": "navRouteAck", "count": len(coordinates)})
        elif message_type == "navInstruction":
          self.publisher.publish_instruction(payload)
          self.send_json(conn, {"type": "navInstructionAck"})
        elif message_type == "navigationStop":
          self.clear_navigation()
          self.send_json(conn, {"type": "navigationStopAck"})
        else:
          self.send_json(conn, {"type": "error", "message": f"unsupported type: {message_type}"})
    except Exception as exc:
      LOGGER.warning("phone_navi client disconnected: %s", exc)
    finally:
      with self.clients_lock:
        self.clients.pop(conn, None)
      try:
        conn.close()
      except OSError:
        pass
      LOGGER.warning("phone_navi client closed: %s", address)

  def websocket_loop(self) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", WEBSOCKET_PORT))
    sock.listen(4)
    LOGGER.warning("phone_navi WebSocket listening on TCP %d", WEBSOCKET_PORT)
    while not self.stop_event.is_set():
      try:
        conn, address = sock.accept()
      except OSError:
        break
      threading.Thread(target=self.handle_client, args=(conn, address), daemon=True).start()
    sock.close()


def main() -> None:
  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
  server = PhoneNaviServer()
  discovery = threading.Thread(target=server.discovery_loop, daemon=True)
  discovery.start()
  try:
    server.websocket_loop()
  except KeyboardInterrupt:
    pass
  finally:
    server.stop_event.set()


if __name__ == "__main__":
  main()
