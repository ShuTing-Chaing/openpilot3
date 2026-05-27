#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C3 Client — 部署到 C3 设备上
与 C3 Director 服务端通信
支持远程指令执行、tmux 故障诊断、心跳保活

通过 openpilot 的 PythonProcess 自动启动：
  PythonProcess("c3-client", "selfdrive.c3_client", always_run),
"""

import asyncio
import importlib
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime

# openpilot 基础模块
from openpilot.system.hardware import HARDWARE, PC
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

# ================= 配置 =================
SERVER_URL = "ws://1.15.136.221:8500"
HEARTBEAT_INTERVAL = 15  # 心跳间隔秒数
RECONNECT_DELAY = 5      # 断线重连等待秒数

# ================= 设备标识 =================
_params = Params()


def get_serial():
  """通过 HARDWARE API 获取设备序列号"""
  try:
    return HARDWARE.get_serial()
  except Exception:
    return os.uname().nodename


def get_dongle_id():
  """通过 Params 获取 dongle_id"""
  try:
    dongle = _params.get("DongleId")
    return dongle if dongle else ""
  except Exception:
    return ""


def get_git_branch():
  """获取当前 openpilot 的分支名"""
  try:
    result = subprocess.run(
      ["git", "rev-parse", "--abbrev-ref", "HEAD"],
      capture_output=True, text=True, timeout=5,
      cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return result.stdout.strip() if result.returncode == 0 else ""
  except Exception:
    return ""


# ================= 指令执行 =================
async def execute_cmd(command, timeout=30):
  """执行 shell 命令，返回 stdout+stderr"""
  try:
    result = await asyncio.wait_for(
      asyncio.create_subprocess_shell(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
      ),
      timeout=timeout
    )
    stdout, _ = await result.communicate()
    return {
      "status": "ok",
      "output": stdout.decode(errors="replace"),
      "returncode": result.returncode
    }
  except asyncio.TimeoutError:
    return {"status": "error", "output": "命令执行超时"}
  except Exception as e:
    return {"status": "error", "output": str(e)}


async def execute_tmux():
  """执行 tmux a 获取当前 tmux 输出（故障诊断）"""
  commands = [
    "tmux capture-pane -t $(tmux list-sessions -F '#{session_name}' 2>/dev/null | head -1) -p -S -200 2>/dev/null",
    "tmux list-sessions 2>/dev/null && tmux send-keys -t $(tmux list-sessions -F '#{session_name}' 2>/dev/null | head -1) '' Enter && sleep 0.5 && tmux capture-pane -t $(tmux list-sessions -F '#{session_name}' 2>/dev/null | head -1) -p -S -200 2>/dev/null",
    "tmux has-session 2>/dev/null && tmux send-keys -t $(tmux list-sessions -F '#{session_name}' 2>/dev/null | head -1) '' && sleep 0.5 && tmux capture-pane -t $(tmux list-sessions -F '#{session_name}' 2>/dev/null | head -1) -p -S -200 2>/dev/null || echo 'TMUX_ERROR: no session found'",
  ]

  tmux_check = await execute_cmd("ps aux | grep tmux | grep -v grep", timeout=3)
  if not tmux_check.get("output", "").strip():
    return {"status": "ok", "output": "⚠️ 设备上未检测到 tmux 进程运行"}

  sessions_result = await execute_cmd("tmux list-sessions 2>&1", timeout=3)
  if "error" in sessions_result.get("output", ""):
    return {"status": "ok", "output": f"⚠️ 无法获取 tmux 会话\n{sessions_result['output']}"}

  result = await execute_cmd(commands[0], timeout=5)
  if result["status"] == "ok" and result.get("output", "").strip():
    session_info = await execute_cmd("tmux list-sessions 2>&1", timeout=3)
    output = f"--- tmux sessions ---\n{session_info.get('output', '')}\n\n--- capture output ---\n{result['output']}"
    return {"status": "ok", "output": output}
  else:
    return {"status": "ok", "output": f"⚠️ 无法捕获 tmux 输出\n{sessions_result.get('output', '')}"}


# ================= 消息处理 =================
async def handle_message(data, ws):
  """处理服务端发来的消息"""
  msg_type = data.get("type")
  msg_id = data.get("id")
  content = data.get("content", "")
  timeout = data.get("timeout", 15)

  if msg_type == "cmd":
    result = await execute_cmd(content, timeout)
  elif msg_type == "tmux":
    result = await execute_tmux()
  elif msg_type == "ping":
    result = {"status": "ok", "output": "pong"}
  else:
    result = {"status": "error", "output": f"未知指令类型: {msg_type}"}

  response = {
    "type": "result",
    "id": msg_id,
    "status": result["status"],
    "output": result.get("output", "")
  }
  try:
    await ws.send(json.dumps(response))
  except Exception as e:
    print(f"[C3] 发送响应失败: {e}")


# ================= 主循环 =================
def _ensure_websockets():
  """确保 websockets 可用，未安装则尝试自动安装"""
  try:
    return importlib.import_module("websockets")
  except ImportError:
    print("[C3] 🔧 未检测到 websockets 模块，尝试自动安装...")
    try:
      subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "websockets", "--break-system-packages"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30
      )
      print("[C3] ✅ websockets 安装成功")
      return importlib.import_module("websockets")
    except Exception:
      print("[C3] ❌ 自动安装失败！请手动执行: pip install websockets")
      sys.exit(1)


async def run():
  """异步主循环（连接、注册、心跳、消息处理、自动重连）"""
  websockets = _ensure_websockets()

  serial = get_serial()
  dongle_id = get_dongle_id()
  git_branch = get_git_branch()

  print(f"[C3 Director Client] 启动 serial={serial} branch={git_branch}")

  while True:
    try:
      async with websockets.connect(
        SERVER_URL,
        ping_interval=20,
        ping_timeout=15
      ) as ws:
        print(f"[C3] ✅ 已连接服务器")

        # 注册（带上分支信息）
        register_msg = json.dumps({
          "type": "register",
          "serial": serial,
          "dongle_id": dongle_id,
          "git_branch": git_branch
        })
        await ws.send(register_msg)
        print(f"[C3] 已注册: {serial} branch={git_branch}")

        async def heartbeat():
          while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
              await ws.send(json.dumps({"type": "heartbeat"}))
            except Exception:
              break

        async def receiver():
          async for message in ws:
            try:
              data = json.loads(message)
              await handle_message(data, ws)
            except json.JSONDecodeError:
              pass
            except Exception as e:
              print(f"[C3] 处理消息出错: {e}")
              traceback.print_exc()

        await asyncio.gather(heartbeat(), receiver())

    except websockets.ConnectionClosed:
      print(f"[C3] 连接断开")
    except ConnectionRefusedError:
      print(f"[C3] 服务器拒绝连接")
    except OSError as e:
      print(f"[C3] 网络错误: {e}")
    except asyncio.TimeoutError:
      print(f"[C3] 连接超时")
    except Exception as e:
      print(f"[C3] 异常: {e}")
      traceback.print_exc()

    print(f"[C3] {RECONNECT_DELAY} 秒后重连...")
    await asyncio.sleep(RECONNECT_DELAY)


# ================= 入口 =================
def main():
  """
  main() 函数 - 供 openpilot PythonProcess 调用
  用法: PythonProcess("c3-client", "selfdrive.c3_client", always_run)
  """
  try:
    asyncio.run(run())
  except KeyboardInterrupt:
    print("[C3] 客户端已停止")
  except Exception as e:
    print(f"[C3] 致命错误: {e}")
    traceback.print_exc()


if __name__ == "__main__":
  main()
