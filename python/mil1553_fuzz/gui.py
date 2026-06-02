from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Dict, List

from .campaign import apply_bus, repeat_cases, run_campaign, write_dry_run
from .ctypes_adapter import CtypesAdapter, default_adapter_path
from .mock_adapter import MockAdapter
from .strategies import StrategyConfig, generate_cases


STRATEGIES = [
    ("cmd_boundary", "Command boundary"),
    ("mode_code", "Mode code"),
    ("broadcast", "Broadcast"),
    ("rt_to_rt", "RT-to-RT"),
    ("data_pattern", "Data pattern"),
    ("random", "Random"),
]


class FuzzGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("1553B BC Fuzz")
        self.geometry("980x720")
        self.minsize(880, 640)

        self.messages: "queue.Queue[str]" = queue.Queue()
        self.worker: threading.Thread | None = None

        self.backend = tk.StringVar(value="mock")
        self.dll_path = tk.StringVar(value=default_adapter_path())
        self.card_index = tk.StringVar(value="0")
        self.channel = tk.StringVar(value="0")
        self.bus = tk.StringVar(value="A")
        self.no_reset = tk.BooleanVar(value=False)
        self.dry_run = tk.BooleanVar(value=False)
        self.rt_targets = tk.StringVar(value="1")
        self.subaddresses = tk.StringVar(value="1")
        self.word_counts = tk.StringVar(value="0,1,2,16,31")
        self.mode_codes = tk.StringVar(value="0,1,2,4,5,8,16,17,31")
        self.limit = tk.StringVar(value="50")
        self.repeat_each = tk.StringVar(value="1")
        self.interval_ms = tk.StringVar(value="200")
        self.timeout_ms = tk.StringVar(value="3000")
        self.seed = tk.StringVar(value="1")
        self.out_path = tk.StringVar(value="runs/gui_latest.jsonl")
        self.strategy_vars: Dict[str, tk.BooleanVar] = {
            name: tk.BooleanVar(value=(name in {"cmd_boundary", "mode_code", "data_pattern"}))
            for name, _ in STRATEGIES
        }

        self._build()
        self.after(100, self._drain_messages)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(3, weight=1)

        backend_frame = ttk.LabelFrame(root, text="Backend")
        backend_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        backend_frame.columnconfigure(5, weight=1)

        ttk.Radiobutton(backend_frame, text="Mock", variable=self.backend, value="mock").grid(row=0, column=0, padx=8, pady=8)
        ttk.Radiobutton(backend_frame, text="Native", variable=self.backend, value="native").grid(row=0, column=1, padx=8, pady=8)
        ttk.Label(backend_frame, text="DLL").grid(row=0, column=2, padx=(12, 4))
        ttk.Entry(backend_frame, textvariable=self.dll_path).grid(row=0, column=3, columnspan=2, sticky="ew", padx=4)
        ttk.Button(backend_frame, text="Browse", command=self._browse_dll).grid(row=0, column=5, padx=8)

        target_frame = ttk.LabelFrame(root, text="Target")
        target_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))

        fields = [
            ("Card", self.card_index),
            ("Channel", self.channel),
            ("Bus", self.bus),
            ("RT targets", self.rt_targets),
            ("Subaddresses", self.subaddresses),
            ("Word counts", self.word_counts),
            ("Mode codes", self.mode_codes),
        ]
        for row, (label, var) in enumerate(fields):
            ttk.Label(target_frame, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=5)
            if label == "Bus":
                ttk.Combobox(target_frame, textvariable=var, values=["A", "B"], width=18, state="readonly").grid(
                    row=row, column=1, sticky="ew", padx=8, pady=5
                )
            else:
                ttk.Entry(target_frame, textvariable=var, width=28).grid(row=row, column=1, sticky="ew", padx=8, pady=5)

        ttk.Checkbutton(target_frame, text="No reset on open", variable=self.no_reset).grid(
            row=len(fields), column=0, columnspan=2, sticky="w", padx=8, pady=6
        )
        ttk.Checkbutton(target_frame, text="Dry run", variable=self.dry_run).grid(
            row=len(fields) + 1, column=0, columnspan=2, sticky="w", padx=8, pady=6
        )

        campaign_frame = ttk.LabelFrame(root, text="Campaign")
        campaign_frame.grid(row=1, column=1, sticky="nsew", pady=(0, 10))
        campaign_frame.columnconfigure(1, weight=1)

        numeric_fields = [
            ("Limit", self.limit),
            ("Repeat each", self.repeat_each),
            ("Interval ms", self.interval_ms),
            ("Timeout ms", self.timeout_ms),
            ("Seed", self.seed),
            ("Output", self.out_path),
        ]
        for row, (label, var) in enumerate(numeric_fields):
            ttk.Label(campaign_frame, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=5)
            ttk.Entry(campaign_frame, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=5)

        ttk.Button(campaign_frame, text="Output...", command=self._browse_output).grid(row=5, column=2, padx=8, pady=5)

        strategy_frame = ttk.LabelFrame(root, text="Strategies")
        strategy_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        for index, (name, label) in enumerate(STRATEGIES):
            ttk.Checkbutton(strategy_frame, text=label, variable=self.strategy_vars[name]).grid(
                row=0, column=index, padx=10, pady=8, sticky="w"
            )

        self.log = scrolledtext.ScrolledText(root, height=18, wrap=tk.WORD)
        self.log.grid(row=3, column=0, columnspan=2, sticky="nsew")

        actions = ttk.Frame(root)
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        actions.columnconfigure(1, weight=1)
        self.run_button = ttk.Button(actions, text="Run", command=self._run)
        self.run_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Clear Log", command=lambda: self.log.delete("1.0", tk.END)).grid(row=0, column=1, sticky="w")

    def _browse_dll(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Adapter DLL", "*.dll"), ("All files", "*.*")])
        if path:
            self.dll_path.set(path)

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".jsonl", filetypes=[("JSONL", "*.jsonl"), ("All files", "*.*")])
        if path:
            self.out_path.set(path)

    def _run(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Running", "A campaign is already running.")
            return

        try:
            config = self._collect_config()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        self.run_button.configure(state=tk.DISABLED)
        self._log("Starting campaign: backend=%s bus=%s cases=%d" % (config["backend"], config["bus"], len(config["cases"])))
        self.worker = threading.Thread(target=self._worker_run, args=(config,), daemon=True)
        self.worker.start()

    def _collect_config(self) -> Dict[str, object]:
        selected = [name for name, var in self.strategy_vars.items() if var.get()]
        if not selected:
            raise ValueError("Select at least one strategy.")

        strategy_config = StrategyConfig(
            rt_targets=_parse_int_list(self.rt_targets.get()),
            subaddresses=_parse_int_list(self.subaddresses.get()),
            word_counts=_parse_int_list(self.word_counts.get()),
            mode_codes=_parse_int_list(self.mode_codes.get()),
            delay_100ns=1000,
            seed=int(self.seed.get()),
        )
        cases = list(generate_cases(selected, strategy_config, int(self.limit.get())))
        cases = list(repeat_cases(list(apply_bus(cases, self.bus.get())), int(self.repeat_each.get())))
        if not cases:
            raise ValueError("No cases generated.")

        return {
            "backend": self.backend.get(),
            "dll_path": self.dll_path.get(),
            "card_index": int(self.card_index.get()),
            "channel": int(self.channel.get()),
            "bus": self.bus.get(),
            "no_reset": self.no_reset.get(),
            "dry_run": self.dry_run.get(),
            "timeout_ms": int(self.timeout_ms.get()),
            "interval_ms": int(self.interval_ms.get()),
            "out_path": self.out_path.get(),
            "cases": cases,
        }

    def _worker_run(self, config: Dict[str, object]) -> None:
        try:
            cases = config["cases"]
            if config["dry_run"]:
                count = write_dry_run(cases, str(config["out_path"]))
                self.messages.put("Dry run wrote %d cases to %s" % (count, config["out_path"]))
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

            count = run_campaign(
                adapter=adapter,
                cases=cases,
                timeout_ms=int(config["timeout_ms"]),
                interval_ms=int(config["interval_ms"]),
                out_path=str(config["out_path"]),
                progress=self._progress,
            )
            self.messages.put("Done. Executed %d cases. Output: %s" % (count, config["out_path"]))
        except Exception as exc:
            self.messages.put("ERROR: %s" % exc)
        finally:
            self.messages.put("__ENABLE_RUN__")

    def _progress(self, index: int, case, record: Dict[str, object]) -> None:
        readback = record.get("readback", {})
        self.messages.put(
            "[%04d] %s CMD1=%s CDP_STS=%s RT_STS1=%s"
            % (
                index,
                case.case_id,
                case.to_dict()["cmd1"],
                readback.get("cdp_sts", "-"),
                readback.get("rt_sts1", "-"),
            )
        )

    def _drain_messages(self) -> None:
        while True:
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                break
            if message == "__ENABLE_RUN__":
                self.run_button.configure(state=tk.NORMAL)
            else:
                self._log(message)
        self.after(100, self._drain_messages)

    def _log(self, message: str) -> None:
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)


def _parse_int_list(text: str) -> List[int]:
    values = []
    for part in text.replace(";", ",").split(","):
        item = part.strip()
        if item:
            values.append(int(item, 0))
    if not values:
        raise ValueError("Expected at least one integer value.")
    return values


def main() -> None:
    FuzzGui().mainloop()


if __name__ == "__main__":
    main()
