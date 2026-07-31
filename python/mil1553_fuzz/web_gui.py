from __future__ import annotations

import argparse
import json
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Deque, Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlparse

from .adapters import BoardAdapter
from .campaign import apply_bus, repeat_cases, run_campaign, write_dry_run
from .ctypes_adapter import CtypesAdapter, default_adapter_path
from .generation import generate_scenario_fuzz_cases
from .mock_adapter import MockAdapter
from .scenarios import ScenarioConfig


STATIC_DIR = Path(__file__).with_name("web_static")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 15530
MAX_REQUEST_BYTES = 1024 * 1024


class WebCampaignController:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.active_adapter: Optional[BoardAdapter] = None
        self.status = "idle"
        self.status_text = "就绪"
        self.status_detail = "等待测试任务"
        self.current = 0
        self.total = 0
        self.output_path = ""
        self.logs: Deque[Dict[str, object]] = deque(maxlen=1200)
        self.log_sequence = 0
        self.last_heartbeat = time.monotonic()
        self.browser_connected = False

    def heartbeat(self) -> None:
        with self.lock:
            self.last_heartbeat = time.monotonic()
            self.browser_connected = True

    def snapshot(self, after_sequence: int = 0) -> Dict[str, object]:
        with self.lock:
            return {
                "status": self.status,
                "status_text": self.status_text,
                "status_detail": self.status_detail,
                "current": self.current,
                "total": self.total,
                "output_path": self.output_path,
                "running": self._is_running_locked(),
                "logs": [
                    item for item in self.logs if int(item["sequence"]) > after_sequence
                ],
                "last_sequence": self.log_sequence,
            }

    def start(self, payload: Dict[str, object]) -> Dict[str, object]:
        config = _parse_campaign_config(payload)
        with self.lock:
            if self._is_running_locked():
                raise ValueError("当前已有测试任务正在运行。")
            self.stop_event.clear()
            self.status = "running"
            self.status_text = "运行中"
            self.status_detail = "正在初始化测试任务"
            self.current = 0
            self.total = len(config["cases"])
            self.output_path = str(config["out_path"])
            self.last_heartbeat = time.monotonic()
            self._append_log_locked(
                "info",
                "开始测试：后端=%s，总线=%s，场景=%d，策略=%d，用例=%d"
                % (
                    "真实板卡" if config["backend"] == "native" else "模拟",
                    config["bus"],
                    len(config["scenarios"]),
                    len(config["strategies"]),
                    len(config["cases"]),
                ),
            )
            self.worker = threading.Thread(
                target=self._run_worker,
                args=(config,),
                name="mil1553-web-campaign",
                daemon=False,
            )
            self.worker.start()
            return self.snapshot()

    def request_stop(self, reason: str = "用户请求停止") -> Dict[str, object]:
        with self.lock:
            if not self._is_running_locked():
                return self.snapshot()
            first_request = not self.stop_event.is_set()
            self.stop_event.set()
            self.status = "stopping"
            self.status_text = "正在停止"
            self.status_detail = "等待当前板卡操作安全退出"
            adapter = self.active_adapter
            if first_request:
                self._append_log_locked("warning", reason)

        if adapter is not None:
            try:
                adapter.stop()
            except Exception as exc:
                self._append_log("warning", "停止板卡发送时返回：%s" % exc)
        return self.snapshot()

    def should_stop_for_missing_browser(self, timeout_seconds: float = 90.0) -> bool:
        with self.lock:
            return (
                self.browser_connected
                and self._is_running_locked()
                and time.monotonic() - self.last_heartbeat > timeout_seconds
            )

    def _run_worker(self, config: Dict[str, object]) -> None:
        adapter: Optional[BoardAdapter] = None
        try:
            cases = config["cases"]
            if config["dry_run"]:
                count = write_dry_run(
                    cases,
                    str(config["out_path"]),
                    self.stop_event,
                )
                with self.lock:
                    self.current = count
                if self.stop_event.is_set():
                    self._finish_stopped("用例生成已停止，共写入 %d 条。" % count)
                else:
                    self._finish_success(
                        "用例生成完成，共写入 %d 条：%s"
                        % (count, config["out_path"])
                    )
                return

            if config["backend"] == "mock":
                adapter = MockAdapter(channel=int(config["channel"]))
            else:
                adapter = CtypesAdapter(
                    dll_path=str(config["dll_path"]),
                    card_index=int(config["card_index"]),
                    channel=int(config["channel"]),
                    timeout_ms=int(config["timeout_ms"]),
                    reset_on_open=not bool(config["no_reset"]),
                )

            with self.lock:
                self.active_adapter = adapter
                self.status_detail = "板卡已就绪，开始执行用例"

            count = run_campaign(
                adapter=adapter,
                cases=cases,
                timeout_ms=int(config["timeout_ms"]),
                interval_ms=int(config["interval_ms"]),
                out_path=str(config["out_path"]),
                progress=self._progress,
                stop_event=self.stop_event,
            )
            if self.stop_event.is_set():
                self._finish_stopped("测试已安全停止，共执行 %d 条用例。" % count)
            else:
                self._finish_success(
                    "测试完成，共执行 %d 条用例。日志：%s"
                    % (count, config["out_path"])
                )
        except Exception as exc:
            if self.stop_event.is_set():
                self._finish_stopped("测试停止过程中返回：%s" % exc)
            else:
                with self.lock:
                    self.status = "error"
                    self.status_text = "执行失败"
                    self.status_detail = str(exc)
                    self._append_log_locked("error", "错误：%s" % exc)
        finally:
            with self.lock:
                if self.active_adapter is adapter:
                    self.active_adapter = None

    def _progress(self, index: int, case, record: Dict[str, object]) -> None:
        readback = record.get("readback", {})
        case_data = case.to_dict()
        with self.lock:
            self.current = index
            self.status_detail = "已执行 %d / %d 条用例" % (index, self.total)
            self._append_log_locked(
                "case",
                "[%04d] 场景=%s 策略=%s CMD1=%s CMD2=%s CDP_STS=%s RT_STS1=%s"
                % (
                    index,
                    case.scenario,
                    case.strategy,
                    case_data["cmd1"],
                    case_data["cmd2"] or "-",
                    readback.get("cdp_sts", "-"),
                    readback.get("rt_sts1", "-"),
                ),
            )

    def _finish_success(self, message: str) -> None:
        with self.lock:
            self.status = "completed"
            self.status_text = "已完成"
            self.status_detail = message
            self._append_log_locked("success", message)

    def _finish_stopped(self, message: str) -> None:
        with self.lock:
            self.status = "stopped"
            self.status_text = "已停止"
            self.status_detail = message
            self._append_log_locked("warning", message)

    def _append_log(self, level: str, message: str) -> None:
        with self.lock:
            self._append_log_locked(level, message)

    def _append_log_locked(self, level: str, message: str) -> None:
        self.log_sequence += 1
        self.logs.append(
            {
                "sequence": self.log_sequence,
                "time": datetime.now().strftime("%H:%M:%S"),
                "level": level,
                "message": message,
            }
        )

    def _is_running_locked(self) -> bool:
        return self.worker is not None and self.worker.is_alive()


class WebGuiRequestHandler(BaseHTTPRequestHandler):
    server: "WebGuiServer"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            after = _query_int(parse_qs(parsed.query), "after", 0)
            self.server.controller.heartbeat()
            self._send_json(self.server.controller.snapshot(after))
            return

        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/app.css": ("app.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        asset = assets.get(parsed.path)
        if asset is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path = STATIC_DIR / asset[0]
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", asset[1])
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/start":
                result = self.server.controller.start(payload)
                self._send_json(result)
            elif parsed.path == "/api/stop":
                reason = str(payload.get("reason", "用户请求停止"))
                self._send_json(self.server.controller.request_stop(reason))
            elif parsed.path == "/api/heartbeat":
                self.server.controller.heartbeat()
                self._send_json({"ok": True})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (TypeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": "服务错误：%s" % exc}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_json(self) -> Dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("无效的请求长度。") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("请求内容过大。")
        if length == 0:
            return {}
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise TypeError("请求内容必须是 JSON 对象。")
        return data

    def _send_json(
        self,
        payload: Dict[str, object],
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class WebGuiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: Tuple[str, int],
        controller: WebCampaignController,
    ) -> None:
        self.controller = controller
        super().__init__(server_address, WebGuiRequestHandler)


def _parse_campaign_config(payload: Dict[str, object]) -> Dict[str, object]:
    scenarios = _string_list(payload.get("scenarios"), "测试场景")
    strategies = _string_list(payload.get("strategies"), "测试策略")
    rt_targets = _int_list(payload.get("rt_targets"), "目标 RT 地址", 0, 30)
    subaddresses = _int_list(payload.get("subaddresses"), "普通子地址", 1, 30)
    word_counts = _int_list(payload.get("word_counts"), "数据字数", 0, 31)
    rt2_source = _int_value(payload.get("rt2_source"), "RT2 发送端", 0, 30)
    rt3_destination = _int_value(
        payload.get("rt3_destination"),
        "RT3 接收端",
        0,
        30,
    )
    limit = _int_value(payload.get("limit"), "用例数量上限", 1, 1_000_000)
    repeat_each = _int_value(payload.get("repeat_each"), "每条重复次数", 1, 10_000)
    interval_ms = _int_value(payload.get("interval_ms"), "发送间隔", 0, 86_400_000)
    timeout_ms = _int_value(payload.get("timeout_ms"), "单条超时", 1, 3_600_000)
    seed = _int_value(payload.get("seed"), "随机种子", 0, 0x7FFFFFFF)
    card_index = _int_value(payload.get("card_index"), "板卡编号", 0, 255)
    channel = _int_value(payload.get("channel"), "通道编号", 0, 255)
    backend = str(payload.get("backend", "mock"))
    if backend not in {"mock", "native"}:
        raise ValueError("运行后端必须是模拟后端或真实板卡。")
    bus = str(payload.get("bus", "A")).upper()
    if bus not in {"A", "B"}:
        raise ValueError("总线通道必须是 A 或 B。")

    scenario_config = ScenarioConfig(
        rt_targets=rt_targets,
        subaddresses=subaddresses,
        word_counts=word_counts,
        rt2_source=rt2_source,
        rt3_destination=rt3_destination,
        delay_100ns=1000,
        seed=seed,
    )
    cases = list(
        generate_scenario_fuzz_cases(
            scenarios,
            strategies,
            scenario_config,
            limit,
        )
    )
    cases = list(repeat_cases(list(apply_bus(cases, bus)), repeat_each))
    if not cases:
        raise ValueError("没有生成任何测试用例，请检查参数。")
    if len(cases) > 1_000_000:
        raise ValueError("重复后用例总数超过 1,000,000，请降低用例数量或重复次数。")

    return {
        "backend": backend,
        "dll_path": str(payload.get("dll_path") or default_adapter_path()),
        "card_index": card_index,
        "channel": channel,
        "bus": bus,
        "no_reset": bool(payload.get("no_reset", False)),
        "dry_run": bool(payload.get("dry_run", False)),
        "timeout_ms": timeout_ms,
        "interval_ms": interval_ms,
        "out_path": str(payload.get("out_path") or "runs/web_latest.jsonl"),
        "scenarios": scenarios,
        "strategies": strategies,
        "cases": cases,
    }


def _string_list(value: object, name: str) -> List[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("%s 必须是列表。" % name)
    result = [str(item) for item in value if str(item)]
    if not result:
        raise ValueError("请至少选择一个%s。" % name)
    return result


def _int_list(
    value: object,
    name: str,
    minimum: int,
    maximum: int,
) -> List[int]:
    if isinstance(value, str):
        items = [item.strip() for item in value.replace(";", ",").split(",")]
        values = [item for item in items if item]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = list(value)
    else:
        raise TypeError("%s 必须是逗号分隔的整数列表。" % name)
    if not values:
        raise ValueError("%s 至少需要填写一个值。" % name)
    return [_int_value(item, name, minimum, maximum) for item in values]


def _int_value(value: object, name: str, minimum: int, maximum: int) -> int:
    try:
        result = int(str(value).strip(), 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("%s 必须是整数。" % name) from exc
    if not minimum <= result <= maximum:
        raise ValueError("%s 必须在 %d 到 %d 之间。" % (name, minimum, maximum))
    return result


def _query_int(query: Dict[str, List[str]], name: str, default: int) -> int:
    try:
        return int(query.get(name, [str(default)])[0])
    except (TypeError, ValueError):
        return default


def _find_available_server(
    controller: WebCampaignController,
    host: str,
    start_port: int,
) -> WebGuiServer:
    last_error: Optional[OSError] = None
    for port in range(start_port, start_port + 10):
        try:
            return WebGuiServer((host, port), controller)
        except OSError as exc:
            last_error = exc
    raise OSError("无法在端口 %d-%d 启动本机界面。" % (start_port, start_port + 9)) from last_error


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="1553B local Web fuzz workspace")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    controller = WebCampaignController()
    server = _find_available_server(controller, args.host, args.port)
    host, port = server.server_address
    url = "http://%s:%d/" % (host, port)

    def monitor_browser() -> None:
        while True:
            time.sleep(1.0)
            if controller.should_stop_for_missing_browser():
                controller.request_stop("界面连接已断开，自动停止测试。")

    threading.Thread(target=monitor_browser, name="mil1553-web-monitor", daemon=True).start()
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    print("1553B fuzz web UI: %s" % url)
    print("Press Ctrl+C to exit.")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        controller.request_stop("服务正在退出，自动停止测试。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
