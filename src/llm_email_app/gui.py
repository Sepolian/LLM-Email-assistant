"""Simple Tkinter GUI for manual testing of the LLM Email assistant.

Features:
- List recent emails (uses `GmailClient.fetch_recent_emails`, currently stubbed)
- Show email body
- Summarize email using `OpenAIClient` (uses stub when no API key)
- Display proposals and allow 'Create event' (respects `DRY_RUN` setting)

This is a light-weight testing UI intended for local development.
"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any

from llm_email_app.email.gmail_client import GmailClient
from llm_email_app.auth.google_oauth import run_local_oauth_flow, delete_cached_token
from llm_email_app.llm.openai_client import OpenAIClient
from llm_email_app.calendar.gcal import GCalClient
from llm_email_app.config import settings


class LLMEmailGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LLM Email — Test GUI")
        self.geometry("1400x1000")

        self.gmail = GmailClient()
        self.llm = OpenAIClient()
        self.gcal = GCalClient()

        self._build_ui()
        # apply dark theme after widgets are created
        self._apply_dark_theme()
        self._load_emails()

    def _build_ui(self):
        # Left: list of emails
        left = ttk.Frame(self)
        # Keep the left frame fixed to the left (doesn't expand horizontally),
        # but allow its internal listbox to take the available vertical space.
        left.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=6, pady=6)

        ttk.Label(left, text="Recent emails:").pack(anchor=tk.W)
        # Let the listbox fill both directions inside the left frame and expand to take available height
        self.emails_listbox = tk.Listbox(left, width=40, height=25)
        self.emails_listbox.pack(fill=tk.BOTH, expand=True)
        self.emails_listbox.bind("<<ListboxSelect>>", self._on_email_select)

        btn_frame = ttk.Frame(left)
        # Keep the button row anchored at the bottom so the listbox keeps full height
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=6)

        signin_btn = ttk.Button(btn_frame, text="Sign In", command=self._on_sign_in)
        signin_btn.pack(side=tk.LEFT, padx=(0, 6))
        signout_btn = ttk.Button(btn_frame, text="Sign Out", command=self._on_sign_out)
        signout_btn.pack(side=tk.LEFT, padx=(0, 6))
        refresh_btn = ttk.Button(btn_frame, text="Refresh (7d)", command=self._load_emails)
        refresh_btn.pack(side=tk.LEFT)

        # Right: email content and controls
        right = ttk.Frame(self)
        # Pack to the left of remaining space so the left frame remains stuck to the left
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)

        ttk.Label(right, text="Email body:").pack(anchor=tk.W)
        self.body_text = tk.Text(right, height=12, wrap=tk.WORD)
        self.body_text.pack(fill=tk.X)

        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill=tk.X, pady=6)
        self.summarize_btn = ttk.Button(btn_frame, text="Summarize", command=self._on_summarize)
        self.summarize_btn.pack(side=tk.LEFT)

        # ttk.Label(btn_frame, text=f"DRY RUN={settings.DRY_RUN}").pack(side=tk.LEFT, padx=8)

        ttk.Label(right, text="Summary:").pack(anchor=tk.W)
        self.summary_text = tk.Text(right, height=6, wrap=tk.WORD)
        self.summary_text.pack(fill=tk.X)

        ttk.Label(right, text="Proposals:").pack(anchor=tk.W)
        # Scrollable proposals area with a fixed max height so controls stay visible on small windows.
        self.proposals_container = ttk.Frame(right)
        # keep a limited height so controls (Create button) are always visible on small windows
        self.proposals_container.pack(fill=tk.BOTH, expand=False, padx=6, pady=6)
        self._proposals_max_height = 240
        self.proposals_container.configure(height=self._proposals_max_height)
        self.proposals_container.pack_propagate(False)

        self.proposals_canvas = tk.Canvas(self.proposals_container, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(self.proposals_container, orient="vertical", command=self.proposals_canvas.yview)
        self.proposals_inner = ttk.Frame(self.proposals_canvas)
        self.proposals_inner.bind(
            "<Configure>",
            lambda e: self.proposals_canvas.configure(scrollregion=self.proposals_canvas.bbox("all"))
        )
        self.proposals_canvas.create_window((0, 0), window=self.proposals_inner, anchor="nw")
        self.proposals_canvas.configure(yscrollcommand=vsb.set, height=self._proposals_max_height)
        self.proposals_canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Keep old name for compatibility with other code paths
        self.proposals_frame = self.proposals_inner

        # Enable mouse-wheel scrolling when cursor is over the proposals canvas.
        self.proposals_canvas.bind("<Enter>", lambda e: self._enable_proposals_mousewheel())
        self.proposals_canvas.bind("<Leave>", lambda e: self._disable_proposals_mousewheel())

        # Single, prominent Create event button below the proposals.
        controls_frame = ttk.Frame(right)
        controls_frame.pack(fill=tk.X, padx=6, pady=(0,6))
        # List of BooleanVars to track which proposals are checked
        self.proposal_vars = []
        

        self.create_event_btn = ttk.Button(
            controls_frame,
            text="Create event",
            command=self._on_create_selected_event,
            state=tk.DISABLED
        )
        self.create_event_btn.pack(side=tk.LEFT, padx=4, pady=4)
        self.create_event_btn.config(width=24)

        ttk.Label(right, text="Log:").pack(anchor=tk.W)
        self.log_text = tk.Text(right, height=6, wrap=tk.WORD)
        self.log_text.pack(fill=tk.X)

    def _log(self, *parts: Any):
        s = " ".join(str(p) for p in parts)
        self.log_text.insert(tk.END, s + "\n")
        self.log_text.see(tk.END)

    def _load_emails(self):
        # Fetch emails from the past 7 days
        try:
            self.emails = self.gmail.fetch_emails_since(days=7, max_results=50)
        except Exception:
            # fallback
            self.emails = self.gmail.fetch_recent_emails(max_results=10)
        self.emails_listbox.delete(0, tk.END)
        for e in self.emails:
            label = f"{e.get('from')} - {e.get('subject')}"
            self.emails_listbox.insert(tk.END, label)
        self._log("Loaded", len(self.emails), "emails")

    def _on_sign_in(self):
        # Run oauth flow in background so UI doesn't block
        def _worker():
            self._log('Starting sign-in flow...')
            try:
                scopes = [
                    'https://www.googleapis.com/auth/gmail.readonly',
                    'https://www.googleapis.com/auth/calendar.events',
                ]
                creds = run_local_oauth_flow(scopes, name='gmail')
                # reinitialize GmailClient with creds
                self.gmail = GmailClient(creds=creds)
                self._log('Sign-in complete')
                self.after(0, self._load_emails)
            except Exception as e:
                self._log('Sign-in error:', e)
                messagebox.showerror('Sign-in error', str(e))

        t = threading.Thread(target=_worker)
        t.daemon = True
        t.start()

    def _on_sign_out(self):
        # Delete cached token and reset GmailClient to stubs
        deleted = delete_cached_token('gmail')
        if deleted:
            self._log('Signed out (token deleted)')
        else:
            self._log('No token found to delete')
        # reset client
        self.gmail = GmailClient(creds=None)
        self._load_emails()

    # ---- proposals canvas mousewheel helpers --------------------------------
    def _enable_proposals_mousewheel(self):
        # Windows / macOS: <MouseWheel> with event.delta
        self.bind_all("<MouseWheel>", self._on_proposals_mousewheel)
        # Linux: button 4/5 events
        self.bind_all("<Button-4>", self._on_proposals_mousewheel)
        self.bind_all("<Button-5>", self._on_proposals_mousewheel)

    def _disable_proposals_mousewheel(self):
        try:
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
        except Exception:
            pass

    def _on_proposals_mousewheel(self, event):
        # cross-platform wheel support
        if hasattr(event, "delta") and event.delta:
            # Windows and macOS: delta is a multiple of 120 (positive up, negative down)
            self.proposals_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        else:
            # X11: use Button-4 (up) / Button-5 (down)
            if getattr(event, "num", None) == 4:
                self.proposals_canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                self.proposals_canvas.yview_scroll(1, "units")
    # --------------------------------------------------------------------------

    def _on_email_select(self, event):
        sel = self.emails_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        e = self.emails[idx]
        self.body_text.delete("1.0", tk.END)
        self.body_text.insert(tk.END, e.get("body", ""))
        # clear summary/proposals
        self.summary_text.delete("1.0", tk.END)
        for child in self.proposals_frame.winfo_children():
            child.destroy()
        # reset proposal checkboxes and disable create button
        self.proposal_vars = []
        self.create_event_btn.config(state=tk.DISABLED)

    def _on_summarize(self):
        sel = self.emails_listbox.curselection()
        if not sel:
            messagebox.showinfo("No email", "Please select an email first")
            return
        idx = sel[0]
        e = self.emails[idx]

        # Run summarization in background thread to keep UI responsive
        t = threading.Thread(target=self._summarize_worker, args=(e,))
        t.daemon = True
        t.start()

    def _summarize_worker(self, email):
        self.summarize_btn.config(state=tk.DISABLED)
        self._log("Summarizing email from", email.get("from"))
        try:
            res = self.llm.summarize_email(
                email.get("body", ""),
                email_received_time=email.get("received"),
                current_time=None,
            )
        except Exception as exc:
            self._log("LLM error:", exc)
            messagebox.showerror("LLM error", str(exc))
            self.summarize_btn.config(state=tk.NORMAL)
            return

        # update UI in main thread
        self.after(0, self._display_summary, res)
        self._log("Summary done")
        self.summarize_btn.config(state=tk.NORMAL)

    def _display_summary(self, res):
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert(tk.END, res.get("text", ""))

        for child in self.proposals_frame.winfo_children():
            child.destroy()

        props = res.get("proposals", []) or []
        # keep current proposals so create button handler can reference selected one
        self.current_proposals = props
        # prepare checkbox variables and disable create button until at least one checked
        self.proposal_vars = []
        self.create_event_btn.config(state=tk.DISABLED)

        bold_font = None
        try:
            # detect and apply a bold font variant if available
            for f in list(tk.font.families()):
                if "bold" in f.lower():
                    bold_font = (f, 10, "bold")
                    break
        except Exception:
            pass

        for idx, p in enumerate(props):
            # use a tk.Frame for the card so we can control bg on hover precisely
            card = tk.Frame(self.proposals_inner, bg=getattr(self, "_card_bg", "#2b2b2b"),
                            relief="groove", bd=1)
            card.pack(fill=tk.X, pady=6, padx=4)

            toprow = tk.Frame(card, bg=getattr(self, "_card_bg", "#2b2b2b"))
            toprow.pack(fill=tk.X, padx=6, pady=(6,0))

            var = tk.BooleanVar(value=False)
            cb = tk.Checkbutton(toprow, variable=var, command=self._on_proposal_toggled,
                                bg=getattr(self, "_card_bg", "#2b2b2b"),
                                fg=getattr(self, "_fg", "#e6e6e6"),
                                selectcolor=getattr(self, "_card_bg", "#2b2b2b"),
                                activebackground=getattr(self, "_card_hover_bg", "#343434"),
                                bd=0)
            cb.pack(side=tk.LEFT, anchor=tk.N)

            title_text = p.get("title") or "Untitled"
            title_lbl = tk.Label(toprow, text=title_text, bg=getattr(self, "_card_bg", "#2b2b2b"),
                                 fg=getattr(self, "_fg", "#e6e6e6"))
            if bold_font:
                try:
                    title_lbl.configure(font=bold_font)
                except Exception:
                    pass
            title_lbl.pack(side=tk.LEFT, anchor=tk.W, padx=(6,0))

            time_text = f"{p.get('start')} — {p.get('end')}"
            time_lbl = tk.Label(card, text=time_text, bg=getattr(self, "_card_bg", "#2b2b2b"),
                                fg=getattr(self, "_muted", "#bfbfbf"))
            time_lbl.pack(anchor=tk.W, padx=36, pady=(2,0))

            # optional short description / location / attendees (truncate if long)
            short = p.get("short") or p.get("description") or ""
            if short:
                lbl = tk.Label(card, text=short, bg=getattr(self, "_card_bg", "#2b2b2b"),
                               fg=getattr(self, "_fg", "#e6e6e6"), wraplength=700, justify=tk.LEFT)
                lbl.pack(anchor=tk.W, padx=36, pady=(4,8))

            self.proposal_vars.append(var)

            # hover handlers: change card and child bg slightly on enter/leave
            def _enter(e, c=card):
                hover = getattr(self, "_card_hover_bg", "#343434")
                c.configure(bg=hover)
                for ch in c.winfo_children():
                    try:
                        ch.configure(bg=hover)
                    except Exception:
                        pass

            def _leave(e, c=card):
                normal = getattr(self, "_card_bg", "#2b2b2b")
                c.configure(bg=normal)
                for ch in c.winfo_children():
                    try:
                        ch.configure(bg=normal)
                    except Exception:
                        pass

            card.bind("<Enter>", _enter)
            card.bind("<Leave>", _leave)
            # also bind hover to descendants
            def _bind_descendants(root, cb_widget):
                for w in root.winfo_children():
                    if w is cb_widget:
                        continue
                    try:
                        w.bind("<Enter>", _enter)
                        w.bind("<Leave>", _leave)
                    except Exception:
                        pass
                    _bind_descendants(w, cb_widget)

            _bind_descendants(card, cb)

            # clicking anywhere on the card toggles the checkbox (except clicks directly on the checkbox)
            def _on_card_click(event, v=var, cb_widget=cb):
                # if the click was directly on the checkbox widget, let the checkbox handle it
                if event.widget is cb_widget:
                    return
                try:
                    v.set(not v.get())
                except Exception:
                    # fallback: toggle by reading current value and setting opposite
                    v.set(False if v.get() else True)
                # notify toggled handler to update controls/state
                try:
                    self._on_proposal_toggled()
                except Exception:
                    pass

            # bind click to card and all descendants (except the checkbox itself)
            def _bind_clicks(root, cb_widget):
                for w in (root,) + tuple(root.winfo_children()):
                    if w is cb_widget:
                        continue
                    try:
                        w.bind("<Button-1>", _on_card_click)
                    except Exception:
                        pass
                    # bind deeper descendants recursively
                    _bind_clicks_recursive(w, cb_widget)

            def _bind_clicks_recursive(widget, cb_widget):
                for child in widget.winfo_children():
                    if child is cb_widget:
                        continue
                    try:
                        child.bind("<Button-1>", _on_card_click)
                    except Exception:
                        pass
                    _bind_clicks_recursive(child, cb_widget)

            # perform bindings
            _bind_clicks(card, cb)

    def _on_proposal_toggled(self):
        # enable create button when any checkbox is checked
        any_checked = any(v.get() for v in getattr(self, "proposal_vars", []))
        self.create_event_btn.config(state=tk.NORMAL if any_checked else tk.DISABLED)

    def _on_create_selected_event(self):
        # collect all checked proposals and create events for each
        selected_indices = [i for i, v in enumerate(getattr(self, "proposal_vars", [])) if v.get()]
        if not selected_indices:
            messagebox.showinfo("No proposal", "Please select one or more proposals first")
            return
        for i in selected_indices:
            proposal = self.current_proposals[i]
            self._on_create_event(proposal)

    def _on_create_event(self, proposal):
        self._log("Create event requested:", proposal)
        if settings.DRY_RUN:
            messagebox.showinfo("DRY RUN", f"Would create event: {proposal.get('title')}")
            self._log("DRY RUN: not creating event")
            return

        # create in background
        t = threading.Thread(target=self._create_event_worker, args=(proposal,))
        t.daemon = True
        t.start()

    def _create_event_worker(self, proposal):
        self._log("Creating event...")
        try:
            event_id = self.gcal.create_event(proposal)
            self._log("Event created id:", event_id)
            messagebox.showinfo("Event created", f"Event id: {event_id}")
        except Exception as exc:
            self._log("Create event error:", exc)
            messagebox.showerror("Create event error", str(exc))

    def _apply_dark_theme(self):
        """Apply a simple dark theme to ttk widgets and native widgets used."""
        bg = "#1f1f1f"
        panel_bg = "#2b2b2b"
        fg = "#e6e6e6"
        muted = "#bfbfbf"
        accent = "#3399ff"
        # card backgrounds: card default is same as panel, hover only a little lighter
        card_bg = panel_bg
        card_hover_bg = "#343434"  # slightly lighter than panel_bg (#2b2b2b)

        # store for other methods to use
        self._bg = bg
        self._panel_bg = panel_bg
        self._card_bg = card_bg
        self._card_hover_bg = card_hover_bg
        self._fg = fg
        self._muted = muted
        self._accent = accent

        # window background
        try:
            self.configure(bg=bg)
        except Exception:
            pass

        style = ttk.Style(self)
        # base theme that is more configurable across platforms
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=panel_bg)
        style.configure("TLabel", background=panel_bg, foreground=fg)
        style.configure("TButton", background=panel_bg, foreground=fg)
        style.map("TButton",
                  background=[("active", accent)],
                  foreground=[("active", "#ffffff")])
        style.configure("TCheckbutton", background=panel_bg, foreground=fg)

        # Apply to main frames (ttk) where applicable
        for w in (self,):
            try:
                w.configure(bg=bg)
            except Exception:
                pass

        # Text widgets (native) — set dark backgrounds and light text, caret color
        for txt in (getattr(self, "body_text", None),
                    getattr(self, "summary_text", None),
                    getattr(self, "log_text", None)):
            if txt:
                txt.configure(bg="#121212", fg=fg, insertbackground=fg, selectbackground="#555555")

        # Listbox (native)
        if getattr(self, "emails_listbox", None):
            self.emails_listbox.configure(bg="#121212", fg=fg, selectbackground="#3399ff", selectforeground="#000000",
                                          highlightthickness=0, relief="flat")

        # Canvas for proposals
        if getattr(self, "proposals_canvas", None):
            try:
                self.proposals_canvas.configure(bg=panel_bg)
            except Exception:
                pass

        # Make TLabel in proposal cards use muted text for meta info by creating a custom style
        style.configure("Muted.TLabel", background=panel_bg, foreground=muted)

        # If proposals inner frame children already exist, tweak their labels/buttons
        if getattr(self, "proposals_inner", None):
            for child in self.proposals_inner.winfo_children():
                try:
                    child.configure(style="TFrame")
                except Exception:
                    pass

        # refresh layout / force redraw
        self.update_idletasks()


def run_gui():
    app = LLMEmailGUI()
    app.mainloop()


if __name__ == '__main__':
    run_gui()
