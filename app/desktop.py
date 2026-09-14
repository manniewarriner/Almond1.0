"""Native desktop interface for Almond."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

from app.desktop_service import AnswerView, ChatView, DesktopService
from app.errors import (
    CalculationError,
    ConfigError,
    ContentPolicyError,
    PermissionDeniedError,
    ProviderError,
    RetrievalError,
)
from app.providers.base import ProviderMessage

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
BACKGROUND = "#2b2b29"
PANEL = "#363432"
PANEL_LIGHT = "#494541"
TEXT = "#fdfaf5"
MUTED = "#d1c8bf"
ACCENT = "#eb5e25"
ACCENT_ACTIVE = "#d94d17"
ERROR = "#ff8d85"


class AlmondDesktop(tk.Tk):
    def __init__(self, service: DesktopService | None = None) -> None:
        super().__init__()
        self.service = service or DesktopService()
        self.title("Almond")
        self.geometry("1060x720")
        self.minsize(860, 600)
        self.configure(bg=BACKGROUND)
        self.chat_history: list[ProviderMessage] = []
        self._results: queue.Queue[tuple[Callable, object, Exception | None]] = queue.Queue()
        icon_path = ASSETS_DIR / "almond.ico"
        if icon_path.is_file():
            self.iconbitmap(default=str(icon_path))
        self._configure_style()
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._drain_results)
        self.after(
            150,
            lambda: self._run_background(
                self.service.start_local_model, self._show_local_model_status
            ),
        )

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BACKGROUND, foreground=TEXT, font=("Segoe UI", 10))
        style.configure(
            "Title.TLabel", background=BACKGROUND, foreground=TEXT, font=("Georgia", 24)
        )
        style.configure(
            "Muted.TLabel", background=BACKGROUND, foreground=MUTED, font=("Segoe UI", 10)
        )
        style.configure(
            "TButton",
            background=PANEL_LIGHT,
            foreground=TEXT,
            borderwidth=0,
            padding=(14, 9),
            font=("Segoe UI Semibold", 10),
        )
        style.map("TButton", background=[("active", "#5c554f")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#18120d")
        style.map("Accent.TButton", background=[("active", ACCENT_ACTIVE)])
        style.configure("TEntry", fieldbackground="#fffaf5", foreground="#18120d", padding=8)
        style.configure("TCombobox", fieldbackground="#fffaf5", foreground="#18120d", padding=7)
        style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=PANEL,
            foreground=MUTED,
            padding=(18, 10),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", ACCENT)],
            foreground=[("selected", "#18120d")],
        )
        style.configure(
            "Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=28
        )
        style.configure("Treeview.Heading", background=PANEL_LIGHT, foreground=TEXT)

    def _build_layout(self) -> None:
        header = ttk.Frame(self, padding=(28, 22, 28, 12))
        header.pack(fill="x")
        logo_path = ASSETS_DIR / "almond-logo.png"
        if logo_path.is_file():
            self.logo_image = tk.PhotoImage(file=str(logo_path)).subsample(18, 18)
            ttk.Label(header, image=self.logo_image).pack(side="left")
        else:
            ttk.Label(header, text="Almond Financial", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Private local assistant", style="Muted.TLabel").pack(
            side="left", padx=(18, 0), pady=(9, 0)
        )
        ttk.Label(header, text="User", style="Muted.TLabel").pack(side="right", padx=(0, 8))
        self.user_var = tk.StringVar(value="local")
        ttk.Entry(header, width=16, textvariable=self.user_var).pack(side="right")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        self._build_chat_tab()
        self._build_ask_tab()
        self._build_search_tab()
        self._build_calculator_tab()
        self._build_audit_tab()
        self._build_health_tab()
        self.tabs.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _new_tab(self, title: str) -> ttk.Frame:
        frame = ttk.Frame(self.tabs, style="Panel.TFrame", padding=24)
        self.tabs.add(frame, text=title)
        return frame

    def _text_area(self, parent: tk.Widget, *, height: int = 10) -> tk.Text:
        widget = tk.Text(
            parent,
            height=height,
            wrap="word",
            bg="#fffaf5",
            fg="#18120d",
            insertbackground="#18120d",
            relief="flat",
            padx=14,
            pady=12,
            font=("Segoe UI", 11),
        )
        return widget

    def _build_chat_tab(self) -> None:
        tab = self._new_tab("General Chat")
        top = ttk.Frame(tab, style="Panel.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="General Chat", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="New chat", command=self._new_chat).pack(side="right")
        self.local_model_status = ttk.Label(
            tab,
            text="Starting local model...",
            style="Muted.TLabel",
        )
        self.local_model_status.pack(anchor="w", pady=(2, 16))
        row = ttk.Frame(tab, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 14))
        self.chat_var = tk.StringVar()
        entry = tk.Entry(
            row,
            textvariable=self.chat_var,
            bg="#fdfaf5",
            fg="#2b2b29",
            insertbackground="#2b2b29",
            relief="flat",
            font=("Segoe UI", 12),
            highlightthickness=2,
            highlightbackground="#d1c8bf",
            highlightcolor=ACCENT,
        )
        entry.pack(side="left", fill="x", expand=True, ipady=9)
        entry.bind("<Return>", lambda _event: self._submit_chat())
        self.chat_button = ttk.Button(
            row, text="Send", style="Accent.TButton", command=self._submit_chat
        )
        self.chat_button.pack(side="left", padx=(10, 0))
        self.chat_text = self._text_area(tab, height=20)
        self.chat_text.pack(fill="both", expand=True)
        self.chat_text.insert("1.0", "Ask a general question. NSFW content is blocked.")
        self.chat_text.configure(state="disabled")

    def _build_ask_tab(self) -> None:
        tab = self._new_tab("Ask")
        ttk.Label(tab, text="Ask approved documents", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            tab,
            text="Answers remain evidence-bound and include source citations.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 16))
        self.answer_text = self._text_area(tab, height=20)
        self.answer_text.pack(fill="both", expand=True)
        row = ttk.Frame(tab, style="Panel.TFrame")
        row.pack(fill="x", pady=(14, 0))
        self.question_var = tk.StringVar()
        question = ttk.Entry(row, textvariable=self.question_var)
        question.pack(side="left", fill="x", expand=True)
        question.bind("<Return>", lambda _event: self._submit_question())
        self.ask_button = ttk.Button(
            row, text="Ask Almond", style="Accent.TButton", command=self._submit_question
        )
        self.ask_button.pack(side="left", padx=(10, 0))

    def _build_search_tab(self) -> None:
        tab = self._new_tab("Search")
        ttk.Label(tab, text="Search documents", style="Title.TLabel").pack(anchor="w")
        row = ttk.Frame(tab, style="Panel.TFrame")
        row.pack(fill="x", pady=(14, 14))
        self.search_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self._submit_search())
        self.search_button = ttk.Button(
            row, text="Search", style="Accent.TButton", command=self._submit_search
        )
        self.search_button.pack(side="left", padx=(10, 0))
        self.search_text = self._text_area(tab, height=22)
        self.search_text.pack(fill="both", expand=True)

    def _build_calculator_tab(self) -> None:
        tab = self._new_tab("Calculator")
        ttk.Label(tab, text="Deterministic calculator", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(tab, text="Calculation", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(24, 6)
        )
        self.calc_kind = tk.StringVar(value="Percentage return")
        ttk.Combobox(
            tab,
            textvariable=self.calc_kind,
            values=("Percentage return", "Absolute change"),
            state="readonly",
            width=28,
        ).grid(row=2, column=0, sticky="ew", padx=(0, 12))
        ttk.Label(tab, text="Start value", style="Muted.TLabel").grid(
            row=3, column=0, sticky="w", pady=(18, 6)
        )
        self.start_var = tk.StringVar()
        ttk.Entry(tab, textvariable=self.start_var).grid(row=4, column=0, sticky="ew", padx=(0, 12))
        ttk.Label(tab, text="End value", style="Muted.TLabel").grid(
            row=3, column=1, sticky="w", pady=(18, 6)
        )
        self.end_var = tk.StringVar()
        ttk.Entry(tab, textvariable=self.end_var).grid(row=4, column=1, sticky="ew")
        ttk.Button(
            tab, text="Calculate", style="Accent.TButton", command=self._submit_calculation
        ).grid(row=5, column=0, sticky="w", pady=(18, 0))
        self.calc_result = ttk.Label(tab, text="", style="Title.TLabel")
        self.calc_result.grid(row=6, column=0, columnspan=2, sticky="w", pady=(28, 0))
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)

    def _build_audit_tab(self) -> None:
        tab = self._new_tab("Audit")
        top = ttk.Frame(tab, style="Panel.TFrame")
        top.pack(fill="x", pady=(0, 12))
        ttk.Label(top, text="Recent activity", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Refresh", command=self._refresh_audit).pack(side="right")
        self.audit_tree = ttk.Treeview(
            tab, columns=("time", "user", "command", "outcome", "summary"), show="headings"
        )
        widths = {"time": 180, "user": 90, "command": 180, "outcome": 80, "summary": 360}
        for name, width in widths.items():
            self.audit_tree.heading(name, text=name.title())
            self.audit_tree.column(name, width=width, minwidth=60)
        self.audit_tree.pack(fill="both", expand=True)

    def _build_health_tab(self) -> None:
        tab = self._new_tab("Health")
        top = ttk.Frame(tab, style="Panel.TFrame")
        top.pack(fill="x", pady=(0, 12))
        ttk.Label(top, text="Local readiness", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Run checks", command=self._refresh_health).pack(side="right")
        self.health_text = self._text_area(tab, height=22)
        self.health_text.pack(fill="both", expand=True)

    def _run_background(self, work: Callable, callback: Callable) -> None:
        def runner() -> None:
            try:
                result = work()
                self._results.put((callback, result, None))
            except Exception as exc:
                self._results.put((callback, None, exc))

        threading.Thread(target=runner, daemon=True).start()

    def _drain_results(self) -> None:
        while True:
            try:
                callback, result, error = self._results.get_nowait()
            except queue.Empty:
                break
            callback(result, error)
        self.after(80, self._drain_results)

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if isinstance(
            error,
            (
                CalculationError,
                ConfigError,
                ContentPolicyError,
                PermissionDeniedError,
                ProviderError,
                RetrievalError,
            ),
        ):
            return str(error)
        if isinstance(error, ValueError):
            return str(error)
        return "The operation failed. Check Almond's Health tab."

    @staticmethod
    def _replace_text(widget: tk.Text, content: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", content)

    def _render_chat(self, temporary: str | None = None) -> None:
        blocks = []
        for message in self.chat_history:
            label = "You" if message.role == "user" else "Almond"
            blocks.append(f"{label}\n{message.content}")
        if temporary:
            blocks.append(temporary)
        content = "\n\n".join(blocks) or "Ask a general question. NSFW content is blocked."
        self.chat_text.configure(state="normal")
        self._replace_text(self.chat_text, content)
        self.chat_text.configure(state="disabled")
        self.chat_text.see("end")

    def _new_chat(self) -> None:
        self.chat_history.clear()
        self.chat_var.set("")
        self._render_chat()

    def _show_local_model_status(self, result: object, error: Exception | None) -> None:
        if error:
            status = self._safe_error(error)
        else:
            status = str(result)
        self.local_model_status.configure(text=status)

    def _submit_chat(self) -> None:
        message = self.chat_var.get().strip()
        if not message:
            return
        history = list(self.chat_history)
        self.chat_button.state(["disabled"])
        self._render_chat("Almond\nThinking...")
        self._run_background(
            lambda: self.service.chat(message, history, self.user_var.get()),
            lambda result, error: self._show_chat(message, result, error),
        )

    def _show_chat(self, message: str, result: object, error: Exception | None) -> None:
        self.chat_button.state(["!disabled"])
        if error:
            self._render_chat(f"Almond\n{self._safe_error(error)}")
            return
        answer = result
        if not isinstance(answer, ChatView):
            self._render_chat("Almond\nThe local model returned an invalid result.")
            return
        self.chat_history.extend(
            [
                ProviderMessage(role="user", content=message),
                ProviderMessage(role="assistant", content=answer.answer),
            ]
        )
        self.chat_var.set("")
        self._render_chat()

    def _submit_question(self) -> None:
        question = self.question_var.get().strip()
        if not question:
            self._replace_text(self.answer_text, "Enter a question.")
            return
        self.ask_button.state(["disabled"])
        self._replace_text(self.answer_text, "Working…")
        self._run_background(
            lambda: self.service.ask(question, self.user_var.get()), self._show_answer
        )

    def _show_answer(self, result: object, error: Exception | None) -> None:
        self.ask_button.state(["!disabled"])
        if error:
            self._replace_text(self.answer_text, self._safe_error(error))
            return
        answer = result
        if not isinstance(answer, AnswerView):
            self._replace_text(self.answer_text, "The operation returned an invalid result.")
            return
        content = answer.answer
        if answer.citations:
            content += "\n\nSources\n" + "\n".join(f"• {item}" for item in answer.citations)
        elif not answer.has_evidence:
            content += "\n\nNo approved-document evidence was found."
        self._replace_text(self.answer_text, content)

    def _submit_search(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            self._replace_text(self.search_text, "Enter search terms.")
            return
        self.search_button.state(["disabled"])
        self._replace_text(self.search_text, "Searching…")
        self._run_background(
            lambda: self.service.search(query, self.user_var.get()), self._show_search
        )

    def _show_search(self, result: object, error: Exception | None) -> None:
        self.search_button.state(["!disabled"])
        if error:
            self._replace_text(self.search_text, self._safe_error(error))
            return
        rows = result if isinstance(result, list) else []
        if not rows:
            self._replace_text(self.search_text, "No evidence found for this query.")
            return
        content = "\n\n".join(
            f"{row.citation}  •  score {row.score:.2f}\n{row.excerpt}" for row in rows
        )
        self._replace_text(self.search_text, content)

    def _submit_calculation(self) -> None:
        try:
            result = self.service.calculate(
                self.calc_kind.get(), self.start_var.get(), self.end_var.get(), self.user_var.get()
            )
        except Exception as exc:
            self.calc_result.configure(text=self._safe_error(exc), foreground=ERROR)
            return
        suffix = "%" if self.calc_kind.get() == "Percentage return" else ""
        self.calc_result.configure(text=f"Result: {result}{suffix}", foreground=TEXT)

    def _on_tab_changed(self, _event: object) -> None:
        selected = self.tabs.tab(self.tabs.select(), "text")
        if selected == "Audit":
            self._refresh_audit()
        elif selected == "Health":
            self._refresh_health()

    def _refresh_audit(self) -> None:
        for item in self.audit_tree.get_children():
            self.audit_tree.delete(item)
        try:
            events = self.service.recent_audit_events()
        except Exception:
            return
        for event in events:
            self.audit_tree.insert(
                "",
                "end",
                values=(
                    event["created_at"],
                    event["user_id"],
                    event["command"],
                    event["outcome"],
                    event["request_summary"],
                ),
            )

    def _refresh_health(self) -> None:
        try:
            items = self.service.health_items()
            content = "\n".join(
                f"{'✓' if item.status.value == 'ok' else '✕'}  {item.name}: {item.detail}"
                for item in items
            )
        except Exception:
            content = "Health check failed."
        self._replace_text(self.health_text, content)

    def _close(self) -> None:
        self.service.stop_local_model()
        self.destroy()


def main() -> None:
    app = AlmondDesktop()
    app.mainloop()


if __name__ == "__main__":
    main()
