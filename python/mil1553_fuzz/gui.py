from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Dict, List, Optional

from .adapters import BoardAdapter
from .campaign import apply_bus, repeat_cases, run_campaign, write_dry_run
from .ctypes_adapter import CtypesAdapter, default_adapter_path
from .generation import generate_scenario_fuzz_cases
from .mock_adapter import MockAdapter
from .scenarios import ScenarioConfig


STRATEGIES = [
    ("bit_level", "位级扰动"),
    ("structured", "结构化模糊"),
    ("semantic", "语义敏感模糊"),
]

SCENARIOS = [
    ("bc_rt_control", "BC→RT 单终端控制下发"),
    ("bc_rt_sync_data", "BC→RT 同步数据"),
    ("bc_broadcast_data", "BC→RT 广播数据"),
    ("bc_broadcast_sync_data", "BC→RTs 广播同步数据"),
    ("bc_broadcast_sync_no_data", "BC→RT 广播同步指令（无数据）"),
    ("rt2_rt3_transfer", "RT2→RT3 数据通信"),
    ("last_command_readback", "Last Command 回读"),
    ("bc_query_rt_status", "BC 查询 RT 状态"),
    ("rt_bc_data_report", "RT→BC 数据上报"),
]


class FuzzGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("1553B BC 模糊测试工具")
        self.geometry("1120x900")
        self.minsize(960, 760)
        self.option_add("*Font", ("Microsoft YaHei UI", 9))

        self.messages: "queue.Queue[object]" = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.adapter_lock = threading.Lock()
        self.active_adapter: Optional[BoardAdapter] = None
        self.closing = False

        self.backend = tk.StringVar(value="mock")
        self.dll_path = tk.StringVar(value=default_adapter_path())
        self.card_index = tk.StringVar(value="0")
        self.channel = tk.StringVar(value="0")
        self.bus = tk.StringVar(value="A")
        self.no_reset = tk.BooleanVar(value=False)
        self.dry_run = tk.BooleanVar(value=False)
        self.rt_targets = tk.StringVar(value="1")
        self.rt2_source = tk.StringVar(value="2")
        self.rt3_destination = tk.StringVar(value="3")
        self.subaddresses = tk.StringVar(value="1")
        self.word_counts = tk.StringVar(value="1,2,16,0")
        self.limit = tk.StringVar(value="100")
        self.repeat_each = tk.StringVar(value="1")
        self.interval_ms = tk.StringVar(value="200")
        self.timeout_ms = tk.StringVar(value="3000")
        self.seed = tk.StringVar(value="1")
        self.out_path = tk.StringVar(value="runs/gui_latest.jsonl")
        self.status_text = tk.StringVar(value="就绪")
        self.scenario_vars: Dict[str, tk.BooleanVar] = {
            name: tk.BooleanVar(value=True) for name, _ in SCENARIOS
        }
        self.strategy_vars: Dict[str, tk.BooleanVar] = {
            name: tk.BooleanVar(value=True) for name, _ in STRATEGIES
        }

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_messages)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(4, weight=1)

        backend_frame = ttk.LabelFrame(root, text="运行后端")
        backend_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        backend_frame.columnconfigure(4, weight=1)

        ttk.Radiobutton(backend_frame, text="模拟后端", variable=self.backend, value="mock").grid(
            row=0, column=0, padx=8, pady=8
        )
        ttk.Radiobutton(backend_frame, text="真实板卡", variable=self.backend, value="native").grid(
            row=0, column=1, padx=8, pady=8
        )
        ttk.Label(backend_frame, text="适配器 DLL").grid(row=0, column=2, padx=(12, 4))
        ttk.Entry(backend_frame, textvariable=self.dll_path).grid(row=0, column=3, columnspan=2, sticky="ew", padx=4)
        ttk.Button(backend_frame, text="浏览...", command=self._browse_dll).grid(row=0, column=5, padx=8)

        target_frame = ttk.LabelFrame(root, text="目标配置")
        target_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))

        fields = [
            ("板卡编号", self.card_index, "entry"),
            ("通道编号", self.channel, "entry"),
            ("总线", self.bus, "bus"),
            ("目标 RT 地址", self.rt_targets, "entry"),
            ("RT2 发送端", self.rt2_source, "entry"),
            ("RT3 接收端", self.rt3_destination, "entry"),
            ("普通子地址", self.subaddresses, "entry"),
            ("数据字数", self.word_counts, "entry"),
        ]
        for row, (label, var, field_type) in enumerate(fields):
            ttk.Label(target_frame, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=5)
            if field_type == "bus":
                ttk.Combobox(target_frame, textvariable=var, values=["A", "B"], width=18, state="readonly").grid(
                    row=row, column=1, sticky="ew", padx=8, pady=5
                )
            else:
                ttk.Entry(target_frame, textvariable=var, width=28).grid(row=row, column=1, sticky="ew", padx=8, pady=5)

        ttk.Checkbutton(target_frame, text="打开时不复位（配合外部 BM）", variable=self.no_reset).grid(
            row=len(fields), column=0, columnspan=2, sticky="w", padx=8, pady=6
        )
        ttk.Checkbutton(target_frame, text="仅生成用例，不发送", variable=self.dry_run).grid(
            row=len(fields) + 1, column=0, columnspan=2, sticky="w", padx=8, pady=6
        )

        campaign_frame = ttk.LabelFrame(root, text="测试任务")
        campaign_frame.grid(row=1, column=1, sticky="nsew", pady=(0, 10))
        campaign_frame.columnconfigure(1, weight=1)

        numeric_fields = [
            ("用例数量上限", self.limit),
            ("每条重复次数", self.repeat_each),
            ("发送间隔（毫秒）", self.interval_ms),
            ("单条超时（毫秒）", self.timeout_ms),
            ("随机种子", self.seed),
            ("日志文件", self.out_path),
        ]
        for row, (label, var) in enumerate(numeric_fields):
            ttk.Label(campaign_frame, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=5)
            ttk.Entry(campaign_frame, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=5)

        ttk.Button(campaign_frame, text="选择...", command=self._browse_output).grid(row=5, column=2, padx=8, pady=5)

        scenario_frame = ttk.LabelFrame(root, text="测试场景")
        scenario_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        for index, (name, label) in enumerate(SCENARIOS):
            ttk.Checkbutton(scenario_frame, text=label, variable=self.scenario_vars[name]).grid(
                row=index // 3,
                column=index % 3,
                padx=10,
                pady=5,
                sticky="w",
            )

        strategy_frame = ttk.LabelFrame(root, text="测试策略")
        strategy_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        for index, (name, label) in enumerate(STRATEGIES):
            ttk.Checkbutton(strategy_frame, text=label, variable=self.strategy_vars[name]).grid(
                row=0, column=index, padx=10, pady=8, sticky="w"
            )

        self.log = scrolledtext.ScrolledText(root, height=14, wrap=tk.WORD, font=("Consolas", 9))
        self.log.grid(row=4, column=0, columnspan=2, sticky="nsew")

        progress_frame = ttk.Frame(root)
        progress_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        progress_frame.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ttk.Label(progress_frame, textvariable=self.status_text, width=24).grid(row=0, column=1, sticky="e")

        actions = ttk.Frame(root)
        actions.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        actions.columnconfigure(3, weight=1)
        self.run_button = ttk.Button(actions, text="开始测试", command=self._run)
        self.run_button.grid(row=0, column=0, padx=(0, 8))
        self.stop_button = ttk.Button(actions, text="停止测试", command=self._request_stop, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="清空日志", command=lambda: self.log.delete("1.0", tk.END)).grid(row=0, column=2)

    def _browse_dll(self) -> None:
        path = filedialog.askopenfilename(
            title="选择板卡适配器 DLL",
            filetypes=[("适配器 DLL", "*.dll"), ("所有文件", "*.*")],
        )
        if path:
            self.dll_path.set(path)

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择测试日志文件",
            defaultextension=".jsonl",
            filetypes=[("JSONL 日志", "*.jsonl"), ("所有文件", "*.*")],
        )
        if path:
            self.out_path.set(path)

    def _run(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("测试正在运行", "当前已有测试任务正在运行。")
            return

        try:
            config = self._collect_config()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self.stop_event.clear()
        self.progress.configure(maximum=len(config["cases"]), value=0)
        self._set_running(True)
        self._log(
            "开始测试：后端=%s，总线=%s，场景=%d，策略=%d，用例数=%d"
            % (
                "真实板卡" if config["backend"] == "native" else "模拟",
                config["bus"],
                len(config["scenarios"]),
                len(config["strategies"]),
                len(config["cases"]),
            )
        )
        self.worker = threading.Thread(target=self._worker_run, args=(config,), daemon=False)
        self.worker.start()

    def _collect_config(self) -> Dict[str, object]:
        selected_scenarios = [name for name, var in self.scenario_vars.items() if var.get()]
        if not selected_scenarios:
            raise ValueError("请至少选择一个测试场景。")
        selected_strategies = [name for name, var in self.strategy_vars.items() if var.get()]
        if not selected_strategies:
            raise ValueError("请至少选择一种变异策略。")

        rt_targets = _parse_int_list(self.rt_targets.get(), "目标 RT 地址", 0, 30)
        rt2_source = _parse_int(self.rt2_source.get(), "RT2 发送端", 0, 30)
        rt3_destination = _parse_int(self.rt3_destination.get(), "RT3 接收端", 0, 30)
        subaddresses = _parse_int_list(self.subaddresses.get(), "普通子地址", 1, 30)
        word_counts = _parse_int_list(self.word_counts.get(), "数据字数", 0, 31)
        limit = _parse_int(self.limit.get(), "用例数量上限", 1, 1_000_000)
        repeat_each = _parse_int(self.repeat_each.get(), "每条重复次数", 1, 10_000)
        interval_ms = _parse_int(self.interval_ms.get(), "发送间隔", 0, 86_400_000)
        timeout_ms = _parse_int(self.timeout_ms.get(), "单条超时", 1, 3_600_000)
        seed = _parse_int(self.seed.get(), "随机种子", 0, 0x7FFFFFFF)
        card_index = _parse_int(self.card_index.get(), "板卡编号", 0, 255)
        channel = _parse_int(self.channel.get(), "通道编号", 0, 255)

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
                selected_scenarios,
                selected_strategies,
                scenario_config,
                limit,
            )
        )
        cases = list(repeat_cases(list(apply_bus(cases, self.bus.get())), repeat_each))
        if not cases:
            raise ValueError("没有生成任何测试用例，请检查参数。")
        if len(cases) > 1_000_000:
            raise ValueError("重复后用例总数超过 1,000,000，请降低用例数量或重复次数。")

        return {
            "backend": self.backend.get(),
            "dll_path": self.dll_path.get(),
            "card_index": card_index,
            "channel": channel,
            "bus": self.bus.get(),
            "no_reset": self.no_reset.get(),
            "dry_run": self.dry_run.get(),
            "timeout_ms": timeout_ms,
            "interval_ms": interval_ms,
            "out_path": self.out_path.get(),
            "scenarios": selected_scenarios,
            "strategies": selected_strategies,
            "cases": cases,
        }

    def _worker_run(self, config: Dict[str, object]) -> None:
        adapter: Optional[BoardAdapter] = None
        try:
            cases = config["cases"]
            if config["dry_run"]:
                count = write_dry_run(cases, str(config["out_path"]), self.stop_event)
                if self.stop_event.is_set():
                    self.messages.put("用例生成已停止，共写入 %d 条。" % count)
                else:
                    self.messages.put("用例生成完成，共写入 %d 条：%s" % (count, config["out_path"]))
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

            with self.adapter_lock:
                self.active_adapter = adapter

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
                self.messages.put("测试已安全停止，共执行 %d 条用例。" % count)
            else:
                self.messages.put("测试完成，共执行 %d 条用例。日志：%s" % (count, config["out_path"]))
        except Exception as exc:
            if self.stop_event.is_set():
                self.messages.put("测试停止过程中返回：%s" % exc)
            else:
                self.messages.put("错误：%s" % exc)
        finally:
            with self.adapter_lock:
                if self.active_adapter is adapter:
                    self.active_adapter = None
            self.messages.put("__RUN_FINISHED__")

    def _request_stop(self) -> None:
        if not self.worker or not self.worker.is_alive():
            return
        if not self.stop_event.is_set():
            self._log("正在请求停止测试，请等待当前板卡操作退出...")
        self.stop_event.set()
        self.status_text.set("正在停止...")
        self.stop_button.configure(state=tk.DISABLED)
        threading.Thread(target=self._stop_active_adapter, daemon=True).start()

    def _stop_active_adapter(self) -> None:
        with self.adapter_lock:
            adapter = self.active_adapter
        if adapter is None:
            return
        try:
            adapter.stop()
        except Exception as exc:
            self.messages.put("停止板卡发送时返回：%s" % exc)

    def _progress(self, index: int, case, record: Dict[str, object]) -> None:
        readback = record.get("readback", {})
        self.messages.put(("__PROGRESS__", index))
        self.messages.put(
            "[%04d] 场景=%s 策略=%s CMD1=%s CMD2=%s CDP_STS=%s RT_STS1=%s"
            % (
                index,
                case.scenario,
                case.strategy,
                case.to_dict()["cmd1"],
                case.to_dict()["cmd2"] or "-",
                readback.get("cdp_sts", "-"),
                readback.get("rt_sts1", "-"),
            )
        )

    def _set_running(self, running: bool) -> None:
        self.run_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_button.configure(state=tk.NORMAL if running else tk.DISABLED)
        self.status_text.set("测试运行中" if running else "就绪")

    def _drain_messages(self) -> None:
        while True:
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                break

            if message == "__RUN_FINISHED__":
                self._set_running(False)
                if self.closing:
                    self.after(0, self._finish_close)
            elif isinstance(message, tuple) and message[0] == "__PROGRESS__":
                self.progress.configure(value=message[1])
                self.status_text.set("已执行 %d / %d" % (message[1], int(float(self.progress["maximum"]))))
            else:
                self._log(str(message))

        if self.winfo_exists():
            self.after(100, self._drain_messages)

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("停止并退出", "测试仍在运行。是否立即停止板卡发送并退出？"):
                return
            self.closing = True
            self.run_button.configure(state=tk.DISABLED)
            self._request_stop()
            self._log("窗口将在测试线程安全退出后关闭。")
            self.after(100, self._finish_close)
            return
        self.destroy()

    def _finish_close(self) -> None:
        if self.worker and self.worker.is_alive():
            self.after(100, self._finish_close)
            return
        self.destroy()

    def _log(self, message: str) -> None:
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)


def _parse_int(text: str, name: str, minimum: int, maximum: int) -> int:
    try:
        value = int(text.strip(), 0)
    except ValueError as exc:
        raise ValueError("%s 必须是整数。" % name) from exc
    if not minimum <= value <= maximum:
        raise ValueError("%s 必须在 %d 到 %d 之间。" % (name, minimum, maximum))
    return value


def _parse_int_list(text: str, name: str, minimum: int, maximum: int) -> List[int]:
    values = []
    for part in text.replace(";", ",").split(","):
        item = part.strip()
        if item:
            values.append(_parse_int(item, name, minimum, maximum))
    if not values:
        raise ValueError("%s 至少需要填写一个值。" % name)
    return values


def main() -> None:
    FuzzGui().mainloop()


if __name__ == "__main__":
    main()
