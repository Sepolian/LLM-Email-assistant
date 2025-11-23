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
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone
from calendar import monthrange

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
        
        self.current_folder = 'INBOX'
        self.current_email_id = None
        self.calendar_events = []

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

        # Email folder selection
        folder_frame = ttk.Frame(left)
        folder_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(folder_frame, text="Folder:").pack(side=tk.LEFT, padx=(0, 4))
        self.folder_var = tk.StringVar(value='INBOX')
        folder_combo = ttk.Combobox(folder_frame, textvariable=self.folder_var, 
                                    values=['INBOX', 'SENT', 'TRASH', 'ARCHIVE'], 
                                    state='readonly', width=12)
        folder_combo.pack(side=tk.LEFT)
        folder_combo.bind('<<ComboboxSelected>>', lambda e: self._on_folder_change())
        
        ttk.Label(left, text="Email List:").pack(anchor=tk.W)
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
        self.compose_btn = ttk.Button(btn_frame, text="Compose", command=self._on_compose)
        self.compose_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.reply_btn = ttk.Button(btn_frame, text="Reply", command=self._on_reply, state=tk.DISABLED)
        self.reply_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.delete_btn = ttk.Button(btn_frame, text="Delete", command=self._on_delete_email, state=tk.DISABLED)
        self.delete_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.archive_btn = ttk.Button(btn_frame, text="Archive", command=self._on_archive, state=tk.DISABLED)
        self.archive_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.mark_read_btn = ttk.Button(btn_frame, text="Mark Read", command=self._on_mark_read, state=tk.DISABLED)
        self.mark_read_btn.pack(side=tk.LEFT, padx=(0, 4))
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
        
        # Add calendar management button
        calendar_btn = ttk.Button(controls_frame, text="Manage Calendar", command=self._open_calendar_window)
        calendar_btn.pack(side=tk.LEFT, padx=4, pady=4)

        ttk.Label(right, text="Log:").pack(anchor=tk.W)
        self.log_text = tk.Text(right, height=6, wrap=tk.WORD)
        self.log_text.pack(fill=tk.X)

    def _log(self, *parts: Any):
        s = " ".join(str(p) for p in parts)
        self.log_text.insert(tk.END, s + "\n")
        self.log_text.see(tk.END)

    def _load_emails(self):
        # 根据当前选择的文件夹加载邮件
        try:
            if self.current_folder == 'INBOX':
                self.emails = self.gmail.fetch_emails_since(days=7, max_results=50)
            else:
                self.emails = self.gmail.fetch_emails_by_label(self.current_folder, max_results=50)
        except Exception:
            # fallback
            self.emails = self.gmail.fetch_recent_emails(max_results=10)
        self.emails_listbox.delete(0, tk.END)
        for e in self.emails:
            label = f"{e.get('from')} - {e.get('subject')}"
            self.emails_listbox.insert(tk.END, label)
        self._log("Loaded", len(self.emails), "emails from", self.current_folder)
    
    def _on_folder_change(self):
        """Called when folder selection changes"""
        self.current_folder = self.folder_var.get()
        self._load_emails()

    def _on_sign_in(self):
        # Run oauth flow in background so UI doesn't block
        def _worker():
            self._log('Starting sign-in flow...')
            try:
                scopes = [
                    'https://mail.google.com/',  # Full Gmail access
                    'https://www.googleapis.com/auth/calendar',  # Full calendar access
                ]
                creds = run_local_oauth_flow(scopes, name='google')
                # reinitialize both GmailClient and GCalClient with creds
                self.gmail = GmailClient(creds=creds)
                self.gcal = GCalClient(creds=creds)
                self._log('Sign-in complete')
                self.after(0, self._load_emails)
            except Exception as e:
                self._log('Sign-in error:', e)
                messagebox.showerror('Sign-in error', str(e))

        t = threading.Thread(target=_worker)
        t.daemon = True
        t.start()

    def _on_sign_out(self):
        # Delete cached token and reset clients to stubs
        deleted = delete_cached_token('google')
        if deleted:
            self._log('Signed out (token deleted)')
        else:
            self._log('No token found to delete')
        # reset clients
        self.gmail = GmailClient(creds=None)
        self.gcal = GCalClient(creds=None)
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
            self.current_email_id = None
            self.reply_btn.config(state=tk.DISABLED)
            self.delete_btn.config(state=tk.DISABLED)
            self.archive_btn.config(state=tk.DISABLED)
            self.mark_read_btn.config(state=tk.DISABLED)
            return
        idx = sel[0]
        e = self.emails[idx]
        self.current_email_id = e.get('id')
        self.body_text.delete("1.0", tk.END)
        self.body_text.insert(tk.END, e.get("body", ""))
        # clear summary/proposals
        self.summary_text.delete("1.0", tk.END)
        for child in self.proposals_frame.winfo_children():
            child.destroy()
        # reset proposal checkboxes and disable create button
        self.proposal_vars = []
        self.create_event_btn.config(state=tk.DISABLED)
        # Enable action buttons
        self.reply_btn.config(state=tk.NORMAL)
        self.delete_btn.config(state=tk.NORMAL)
        self.archive_btn.config(state=tk.NORMAL)
        self.mark_read_btn.config(state=tk.NORMAL)

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
                email_sender=email.get("from"),
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

    def _on_compose(self):
        """Open compose email dialog"""
        dialog = tk.Toplevel(self)
        dialog.title("Compose Email")
        dialog.geometry("600x500")
        
        ttk.Label(dialog, text="To:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        to_entry = tk.Entry(dialog, width=60)
        to_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Label(dialog, text="Subject:").pack(anchor=tk.W, padx=10)
        subject_entry = tk.Entry(dialog, width=60)
        subject_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Label(dialog, text="Body:").pack(anchor=tk.W, padx=10)
        body_text = tk.Text(dialog, height=15, wrap=tk.WORD)
        body_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        def send_email():
            to = to_entry.get().strip()
            subject = subject_entry.get().strip()
            body = body_text.get("1.0", tk.END).strip()
            if not to or not subject:
                messagebox.showwarning("Input Error", "Please fill in recipient and subject")
                return
            dialog.destroy()
            t = threading.Thread(target=self._send_email_worker, args=(to, subject, body))
            t.daemon = True
            t.start()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Send", command=send_email).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

    def _send_email_worker(self, to, subject, body):
        """Send email in background thread"""
        self._log("Sending email...")
        try:
            email_id = self.gmail.send_email(to, subject, body)
            self._log("Email sent, ID:", email_id)
            messagebox.showinfo("Success", "Email sent successfully")
            self.after(0, self._load_emails)
        except Exception as exc:
            self._log("Send email error:", exc)
            messagebox.showerror("Send Error", str(exc))

    def _on_reply(self):
        """Reply to currently selected email"""
        if not self.current_email_id:
            messagebox.showwarning("No Email", "Please select an email first")
            return
        
        # Get current email info
        sel = self.emails_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        e = self.emails[idx]
        
        dialog = tk.Toplevel(self)
        dialog.title("Reply Email")
        dialog.geometry("600x400")
        
        ttk.Label(dialog, text="To:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        to_entry = tk.Entry(dialog, width=60)
        to_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        # Auto-fill sender
        from_addr = e.get('from', '').split('<')[-1].replace('>', '').strip()
        to_entry.insert(0, from_addr)
        to_entry.config(state='readonly')
        
        ttk.Label(dialog, text="Subject:").pack(anchor=tk.W, padx=10)
        subject_entry = tk.Entry(dialog, width=60)
        subject_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        subject_entry.insert(0, f"Re: {e.get('subject', '')}")
        
        ttk.Label(dialog, text="Body:").pack(anchor=tk.W, padx=10)
        body_text = tk.Text(dialog, height=12, wrap=tk.WORD)
        body_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        def send_reply():
            body = body_text.get("1.0", tk.END).strip()
            if not body:
                messagebox.showwarning("Input Error", "Please fill in reply content")
                return
            dialog.destroy()
            t = threading.Thread(target=self._reply_email_worker, args=(self.current_email_id, body))
            t.daemon = True
            t.start()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Send", command=send_reply).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

    def _reply_email_worker(self, message_id, body):
        """Reply to email in background thread"""
        self._log("Replying to email...")
        try:
            email_id = self.gmail.reply_to_email(message_id, body)
            self._log("Reply sent, ID:", email_id)
            messagebox.showinfo("Success", "Reply sent successfully")
            self.after(0, self._load_emails)
        except Exception as exc:
            self._log("Reply email error:", exc)
            messagebox.showerror("Reply Error", str(exc))

    def _on_delete_email(self):
        """Delete currently selected email"""
        if not self.current_email_id:
            messagebox.showwarning("No Email", "Please select an email first")
            return
        
        if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this email?"):
            return
        
        t = threading.Thread(target=self._delete_email_worker, args=(self.current_email_id,))
        t.daemon = True
        t.start()

    def _delete_email_worker(self, message_id):
        """Delete email in background thread"""
        self._log("Deleting email...")
        try:
            success = self.gmail.delete_email(message_id)
            if success:
                self._log("Email deleted")
                messagebox.showinfo("Success", "Email deleted successfully")
                self.after(0, self._load_emails)
            else:
                messagebox.showerror("Error", "Failed to delete email")
        except Exception as exc:
            self._log("Delete email error:", exc)
            messagebox.showerror("Delete Error", str(exc))

    def _on_archive(self):
        """Archive currently selected email"""
        if not self.current_email_id:
            messagebox.showwarning("No Email", "Please select an email first")
            return
        
        t = threading.Thread(target=self._archive_email_worker, args=(self.current_email_id,))
        t.daemon = True
        t.start()

    def _archive_email_worker(self, message_id):
        """Archive email in background thread"""
        self._log("Archiving email...")
        try:
            success = self.gmail.archive_email(message_id)
            if success:
                self._log("Email archived")
                messagebox.showinfo("Success", "Email archived successfully")
                self.after(0, self._load_emails)
            else:
                messagebox.showerror("Error", "Failed to archive email")
        except Exception as exc:
            self._log("Archive email error:", exc)
            messagebox.showerror("Archive Error", str(exc))

    def _on_mark_read(self):
        """Mark currently selected email as read"""
        if not self.current_email_id:
            messagebox.showwarning("No Email", "Please select an email first")
            return
        
        t = threading.Thread(target=self._mark_read_worker, args=(self.current_email_id, True))
        t.daemon = True
        t.start()

    def _mark_read_worker(self, message_id, read):
        """Mark email as read/unread in background thread"""
        self._log("Marking email as read..." if read else "Marking email as unread...")
        try:
            success = self.gmail.mark_as_read(message_id, read)
            if success:
                self._log("Email marked")
                messagebox.showinfo("Success", "Email marked as read" if read else "Email marked as unread")
                self.after(0, self._load_emails)
            else:
                messagebox.showerror("Error", "Failed to mark email")
        except Exception as exc:
            self._log("Mark email error:", exc)
            messagebox.showerror("Mark Error", str(exc))

    def _open_calendar_window(self):
        """Open calendar management window (month grid view)"""
        if hasattr(self, '_calendar_window') and self._calendar_window.winfo_exists():
            self._calendar_window.lift()
            return
        
        window = tk.Toplevel(self)
        window.title("Calendar Management")
        window.geometry("1200x800")
        self._calendar_window = window
        
        # Apply dark theme
        window.configure(bg="#1f1f1f")
        
        # Top navigation bar
        nav_frame = ttk.Frame(window)
        nav_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Month navigation
        nav_left_frame = ttk.Frame(nav_frame)
        nav_left_frame.pack(side=tk.LEFT)
        
        self._calendar_view_month = datetime.now().month
        self._calendar_view_year = datetime.now().year
        
        prev_btn = ttk.Button(nav_left_frame, text="◀", width=3, command=lambda: self._calendar_navigate(-1))
        prev_btn.pack(side=tk.LEFT, padx=2)
        
        today_btn = ttk.Button(nav_left_frame, text="Today", command=self._calendar_go_today)
        today_btn.pack(side=tk.LEFT, padx=2)
        
        next_btn = ttk.Button(nav_left_frame, text="▶", width=3, command=lambda: self._calendar_navigate(1))
        next_btn.pack(side=tk.LEFT, padx=2)
        
        # Month/year display
        self._calendar_month_label = ttk.Label(nav_frame, text="", font=('Arial', 14, 'bold'))
        self._calendar_month_label.pack(side=tk.LEFT, padx=20)
        
        # Right side action buttons
        nav_right_frame = ttk.Frame(nav_frame)
        nav_right_frame.pack(side=tk.RIGHT)
        
        refresh_btn = ttk.Button(nav_right_frame, text="Refresh", command=self._calendar_refresh)
        refresh_btn.pack(side=tk.LEFT, padx=2)
        
        add_btn = ttk.Button(nav_right_frame, text="+ Add Event", command=lambda: self._on_add_calendar_event(window))
        add_btn.pack(side=tk.LEFT, padx=2)
        
        # Main content area
        main_frame = ttk.Frame(window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Calendar grid container
        calendar_container = tk.Frame(main_frame, bg="#1f1f1f")
        calendar_container.pack(fill=tk.BOTH, expand=True)
        
        # Store calendar grid reference
        window.calendar_container = calendar_container
        window.calendar_events = {}
        
        # Initialize calendar view
        self._calendar_refresh()
    
    def _calendar_navigate(self, direction):
        """Navigate to previous or next month"""
        self._calendar_view_month += direction
        if self._calendar_view_month > 12:
            self._calendar_view_month = 1
            self._calendar_view_year += 1
        elif self._calendar_view_month < 1:
            self._calendar_view_month = 12
            self._calendar_view_year -= 1
        self._calendar_refresh()
    
    def _calendar_go_today(self):
        """Jump to today"""
        now = datetime.now()
        self._calendar_view_month = now.month
        self._calendar_view_year = now.year
        self._calendar_refresh()
    
    def _calendar_refresh(self):
        """Refresh calendar view"""
        if not hasattr(self, '_calendar_window') or not self._calendar_window.winfo_exists():
            return
        
        window = self._calendar_window
        container = window.calendar_container
        
        # Clear existing content
        for widget in container.winfo_children():
            widget.destroy()
        
        # Update month label
        month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December']
        month_name = month_names[self._calendar_view_month - 1]
        self._calendar_month_label.config(text=f"{month_name} {self._calendar_view_year}")
        
        # Load events
        def load_events_worker():
            try:
                # Calculate month start and end times
                first_day = datetime(self._calendar_view_year, self._calendar_view_month, 1, tzinfo=timezone.utc)
                if self._calendar_view_month == 12:
                    last_day = datetime(self._calendar_view_year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
                else:
                    last_day = datetime(self._calendar_view_year, self._calendar_view_month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
                
                time_min = first_day.isoformat()
                time_max = last_day.isoformat()
                
                events = self.gcal.list_events(max_results=250, time_min=time_min, time_max=time_max)
                
                # Organize events by date
                events_by_date = {}
                for event in events:
                    start = event.get('start', {})
                    if 'dateTime' in start:
                        event_date = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                        date_key = event_date.date()
                    elif 'date' in start:
                        event_date = datetime.fromisoformat(start['date'])
                        date_key = event_date.date()
                    else:
                        continue
                    
                    if date_key not in events_by_date:
                        events_by_date[date_key] = []
                    events_by_date[date_key].append(event)
                
                window.calendar_events = events_by_date
                self.after(0, lambda: self._render_calendar_grid(container, events_by_date))
            except Exception as e:
                self._log("Load calendar events error:", e)
                self.after(0, lambda: self._render_calendar_grid(container, {}))
        
        # Load events in background thread
        t = threading.Thread(target=load_events_worker)
        t.daemon = True
        t.start()
        
        # Grid will be rendered after events are loaded (or on error)
    
    def _render_calendar_grid(self, container, events_by_date: Dict):
        """Render calendar grid"""
        # Weekday headers
        weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        header_frame = tk.Frame(container, bg="#2b2b2b")
        header_frame.pack(fill=tk.X, pady=(0, 2))
        
        for i, day_name in enumerate(weekdays):
            day_label = tk.Label(header_frame, text=day_name, bg="#2b2b2b", fg="#e6e6e6",
                               font=('Arial', 10, 'bold'), width=12, anchor='center')
            day_label.grid(row=0, column=i, padx=1, pady=1, sticky='nsew')
            header_frame.columnconfigure(i, weight=1)
        
        # Calculate which weekday the first day of the month is (0=Monday, 6=Sunday, convert to 0=Sunday)
        first_day = datetime(self._calendar_view_year, self._calendar_view_month, 1)
        first_weekday = (first_day.weekday() + 1) % 7  # weekday() returns 0=Monday, 6=Sunday, convert to 0=Sunday
        days_in_month = monthrange(self._calendar_view_year, self._calendar_view_month)[1]
        
        # Create grid
        grid_frame = tk.Frame(container, bg="#1f1f1f")
        grid_frame.pack(fill=tk.BOTH, expand=True)
        
        today = datetime.now().date()
        current_month = datetime(self._calendar_view_year, self._calendar_view_month, 1).date()
        
        # Calculate total days to display (including previous and next month dates)
        total_cells = 42  # 6 rows x 7 columns
        start_offset = first_weekday
        
        for i in range(total_cells):
            row = i // 7
            col = i % 7
            
            if row == 0 and col == 0:
                # 创建第一行
                row_frame = tk.Frame(grid_frame, bg="#1f1f1f")
                row_frame.grid(row=row, column=0, columnspan=7, sticky='nsew', padx=1, pady=1)
                grid_frame.rowconfigure(row, weight=1)
            elif i % 7 == 0:
                # 创建新行
                row_frame = tk.Frame(grid_frame, bg="#1f1f1f")
                row_frame.grid(row=row, column=0, columnspan=7, sticky='nsew', padx=1, pady=1)
                grid_frame.rowconfigure(row, weight=1)
            
            day_num = i - start_offset + 1
            
            # Determine if in current month
            if day_num < 1:
                # Previous month dates
                if self._calendar_view_month == 1:
                    prev_month = 12
                    prev_year = self._calendar_view_year - 1
                else:
                    prev_month = self._calendar_view_month - 1
                    prev_year = self._calendar_view_year
                prev_days = monthrange(prev_year, prev_month)[1]
                actual_day = prev_days + day_num
                date_obj = datetime(prev_year, prev_month, actual_day).date()
                is_current_month = False
            elif day_num > days_in_month:
                # Next month dates
                actual_day = day_num - days_in_month
                if self._calendar_view_month == 12:
                    next_month = 1
                    next_year = self._calendar_view_year + 1
                else:
                    next_month = self._calendar_view_month + 1
                    next_year = self._calendar_view_year
                date_obj = datetime(next_year, next_month, actual_day).date()
                is_current_month = False
            else:
                # Current month dates
                actual_day = day_num
                date_obj = datetime(self._calendar_view_year, self._calendar_view_month, actual_day).date()
                is_current_month = True
            
            # Create date cell
            cell_bg = "#2b2b2b" if is_current_month else "#1a1a1a"
            cell_fg = "#e6e6e6" if is_current_month else "#666666"
            
            # Highlight today
            if date_obj == today:
                cell_bg = "#3399ff"
                cell_fg = "#ffffff"
            
            day_frame = tk.Frame(row_frame, bg=cell_bg, relief=tk.RAISED, bd=1)
            day_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1)
            
            # Date number
            day_label = tk.Label(day_frame, text=str(actual_day), bg=cell_bg, fg=cell_fg,
                               font=('Arial', 10, 'bold' if date_obj == today else 'normal'),
                               anchor='nw', padx=4, pady=2)
            day_label.pack(anchor='nw', fill=tk.X)
            
            # Events list
            events_frame = tk.Frame(day_frame, bg=cell_bg)
            events_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
            
            if date_obj in events_by_date:
                events = events_by_date[date_obj]
                for event in events[:3]:  # Show max 3 events
                    summary = event.get('summary', 'Untitled')
                    # Truncate long titles
                    if len(summary) > 15:
                        summary = summary[:12] + '...'
                    
                    event_color = "#4caf50"  # Green
                    event_label = tk.Label(events_frame, text=summary, bg=event_color, fg="#ffffff",
                                         font=('Arial', 8), anchor='w', padx=4, pady=1)
                    event_label.pack(fill=tk.X, pady=1)
                    event_label.bind("<Button-1>", lambda e, evt=event: self._on_calendar_event_click(evt))
                    day_label.bind("<Button-1>", lambda e, d=date_obj: self._on_calendar_date_click(d))
                
                if len(events) > 3:
                    more_label = tk.Label(events_frame, text=f"+{len(events) - 3} more", bg=cell_bg, fg="#999999",
                                        font=('Arial', 7), anchor='w', padx=4)
                    more_label.pack(fill=tk.X, pady=1)
            
            # Double-click date to add event
            day_frame.bind("<Double-Button-1>", lambda e, d=date_obj: self._on_calendar_date_double_click(d))
            day_label.bind("<Double-Button-1>", lambda e, d=date_obj: self._on_calendar_date_double_click(d))
        
        # Configure column weights
        for col in range(7):
            grid_frame.columnconfigure(col, weight=1)
    
    def _on_calendar_event_click(self, event):
        """Click on calendar event"""
        # Show event details dialog
        dialog = tk.Toplevel(self._calendar_window)
        dialog.title("Event Details")
        dialog.geometry("500x400")
        
        summary = event.get('summary', 'Untitled')
        description = event.get('description', '')
        start = event.get('start', {})
        end = event.get('end', {})
        location = event.get('location', '')
        
        ttk.Label(dialog, text="Title:", font=('Arial', 10, 'bold')).pack(anchor=tk.W, padx=10, pady=(10, 0))
        ttk.Label(dialog, text=summary, font=('Arial', 12)).pack(anchor=tk.W, padx=20, pady=2)
        
        if start.get('dateTime'):
            start_time = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
            ttk.Label(dialog, text=f"Start: {start_time.strftime('%Y-%m-%d %H:%M')}").pack(anchor=tk.W, padx=20, pady=2)
        elif start.get('date'):
            ttk.Label(dialog, text=f"Date: {start['date']}").pack(anchor=tk.W, padx=20, pady=2)
        
        if location:
            ttk.Label(dialog, text=f"Location: {location}").pack(anchor=tk.W, padx=20, pady=2)
        
        if description:
            ttk.Label(dialog, text="Description:").pack(anchor=tk.W, padx=10, pady=(10, 0))
            desc_text = tk.Text(dialog, height=8, wrap=tk.WORD)
            desc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            desc_text.insert("1.0", description)
            desc_text.config(state=tk.DISABLED)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Edit", command=lambda: (dialog.destroy(), self._on_edit_calendar_event_by_id(event.get('id')))).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=lambda: (dialog.destroy(), self._on_delete_calendar_event_by_id(event.get('id')))).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)
    
    def _on_calendar_date_click(self, date_obj):
        """Single click on date (can be extended)"""
        pass
    
    def _on_calendar_date_double_click(self, date_obj):
        """Double-click date to add event"""
        # Use selected date as default start time
        start_datetime = datetime.combine(date_obj, datetime.min.time())
        start_str = start_datetime.isoformat()
        end_str = (start_datetime + timedelta(hours=1)).isoformat()
        
        dialog = tk.Toplevel(self._calendar_window)
        dialog.title("Add Calendar Event")
        dialog.geometry("500x400")
        
        ttk.Label(dialog, text="Title:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        title_entry = tk.Entry(dialog, width=50)
        title_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Label(dialog, text="Start Time (YYYY-MM-DDTHH:MM:SS):").pack(anchor=tk.W, padx=10)
        start_entry = tk.Entry(dialog, width=50)
        start_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        start_entry.insert(0, start_str)
        
        ttk.Label(dialog, text="End Time (YYYY-MM-DDTHH:MM:SS):").pack(anchor=tk.W, padx=10)
        end_entry = tk.Entry(dialog, width=50)
        end_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        end_entry.insert(0, end_str)
        
        ttk.Label(dialog, text="Description:").pack(anchor=tk.W, padx=10)
        desc_text = tk.Text(dialog, height=8, wrap=tk.WORD)
        desc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        def create_event():
            title = title_entry.get().strip()
            start = start_entry.get().strip()
            end = end_entry.get().strip()
            description = desc_text.get("1.0", tk.END).strip()
            if not title or not start or not end:
                messagebox.showwarning("Input Error", "Please fill in title, start time, and end time")
                return
            dialog.destroy()
            t = threading.Thread(target=self._add_calendar_event_worker, args=(title, start, end, description))
            t.daemon = True
            t.start()
            # Refresh calendar view
            self.after(1000, self._calendar_refresh)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Create", command=create_event).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
    
    def _on_edit_calendar_event_by_id(self, event_id):
        """Edit event by event ID"""
        if not event_id:
            return
        event = self.gcal.get_event(event_id)
        if not event:
            messagebox.showerror("Error", "Unable to get event information")
            return
        
        # Use existing edit dialog
        dialog = tk.Toplevel(self._calendar_window)
        dialog.title("Edit Calendar Event")
        dialog.geometry("500x400")
        
        ttk.Label(dialog, text="Title:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        title_entry = tk.Entry(dialog, width=50)
        title_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        title_entry.insert(0, event.get('summary', ''))
        
        ttk.Label(dialog, text="Start Time (YYYY-MM-DDTHH:MM:SS):").pack(anchor=tk.W, padx=10)
        start_entry = tk.Entry(dialog, width=50)
        start_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        start_val = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))
        start_entry.insert(0, start_val)
        
        ttk.Label(dialog, text="End Time (YYYY-MM-DDTHH:MM:SS):").pack(anchor=tk.W, padx=10)
        end_entry = tk.Entry(dialog, width=50)
        end_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        end_val = event.get('end', {}).get('dateTime', event.get('end', {}).get('date', ''))
        end_entry.insert(0, end_val)
        
        ttk.Label(dialog, text="Description:").pack(anchor=tk.W, padx=10)
        desc_text = tk.Text(dialog, height=8, wrap=tk.WORD)
        desc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        desc_text.insert("1.0", event.get('description', ''))
        
        def update_event():
            title = title_entry.get().strip()
            start = start_entry.get().strip()
            end = end_entry.get().strip()
            description = desc_text.get("1.0", tk.END).strip()
            if not title or not start or not end:
                messagebox.showwarning("Input Error", "Please fill in title, start time, and end time")
                return
            dialog.destroy()
            t = threading.Thread(target=self._edit_calendar_event_worker, args=(event_id, title, start, end, description))
            t.daemon = True
            t.start()
            # Refresh calendar view
            self.after(1000, self._calendar_refresh)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Save", command=update_event).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
    
    def _on_delete_calendar_event_by_id(self, event_id):
        """Delete event by event ID"""
        if not event_id:
            return
        if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this event?"):
            return
        
        t = threading.Thread(target=self._delete_calendar_event_worker, args=(event_id,))
        t.daemon = True
        t.start()
        # Refresh calendar view
        self.after(1000, self._calendar_refresh)

    def _on_add_calendar_event(self, parent_window=None):
        """Add calendar event"""
        dialog = tk.Toplevel(parent_window or self)
        dialog.title("Add Calendar Event")
        dialog.geometry("500x400")
        
        ttk.Label(dialog, text="Title:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        title_entry = tk.Entry(dialog, width=50)
        title_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Label(dialog, text="Start Time (YYYY-MM-DDTHH:MM:SS):").pack(anchor=tk.W, padx=10)
        start_entry = tk.Entry(dialog, width=50)
        start_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Label(dialog, text="End Time (YYYY-MM-DDTHH:MM:SS):").pack(anchor=tk.W, padx=10)
        end_entry = tk.Entry(dialog, width=50)
        end_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Label(dialog, text="Description:").pack(anchor=tk.W, padx=10)
        desc_text = tk.Text(dialog, height=8, wrap=tk.WORD)
        desc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        def create_event():
            title = title_entry.get().strip()
            start = start_entry.get().strip()
            end = end_entry.get().strip()
            description = desc_text.get("1.0", tk.END).strip()
            if not title or not start or not end:
                messagebox.showwarning("Input Error", "Please fill in title, start time, and end time")
                return
            dialog.destroy()
            t = threading.Thread(target=self._add_calendar_event_worker, args=(title, start, end, description))
            t.daemon = True
            t.start()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Create", command=create_event).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

    def _add_calendar_event_worker(self, title, start, end, description):
        """Add calendar event in background thread"""
        self._log("Creating calendar event...")
        try:
            proposal = {
                'title': title,
                'start': start,
                'end': end,
                'notes': description,
                'timeZone': 'UTC'
            }
            event_id = self.gcal.create_event(proposal)
            self._log("Calendar event created, ID:", event_id)
            messagebox.showinfo("Success", "Calendar event created successfully")
            if hasattr(self, '_calendar_window') and self._calendar_window.winfo_exists():
                # Refresh calendar window
                self.after(1000, self._calendar_refresh)
        except Exception as exc:
            self._log("Create calendar event error:", exc)
            messagebox.showerror("Create Error", str(exc))

    def _on_edit_calendar_event(self, parent_window, calendar_listbox):
        """Edit selected calendar event"""
        sel = calendar_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select an event first")
            return
        
        idx = sel[0]
        if not hasattr(parent_window, 'calendar_events'):
            messagebox.showerror("Error", "Unable to get event list")
            return
        
        event = parent_window.calendar_events[idx]
        event_id = event.get('id')
        
        dialog = tk.Toplevel(parent_window)
        dialog.title("Edit Calendar Event")
        dialog.geometry("500x400")
        
        ttk.Label(dialog, text="Title:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        title_entry = tk.Entry(dialog, width=50)
        title_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        title_entry.insert(0, event.get('summary', ''))
        
        ttk.Label(dialog, text="Start Time (YYYY-MM-DDTHH:MM:SS):").pack(anchor=tk.W, padx=10)
        start_entry = tk.Entry(dialog, width=50)
        start_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        start_val = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))
        start_entry.insert(0, start_val)
        
        ttk.Label(dialog, text="End Time (YYYY-MM-DDTHH:MM:SS):").pack(anchor=tk.W, padx=10)
        end_entry = tk.Entry(dialog, width=50)
        end_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        end_val = event.get('end', {}).get('dateTime', event.get('end', {}).get('date', ''))
        end_entry.insert(0, end_val)
        
        ttk.Label(dialog, text="Description:").pack(anchor=tk.W, padx=10)
        desc_text = tk.Text(dialog, height=8, wrap=tk.WORD)
        desc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        desc_text.insert("1.0", event.get('description', ''))
        
        def update_event():
            title = title_entry.get().strip()
            start = start_entry.get().strip()
            end = end_entry.get().strip()
            description = desc_text.get("1.0", tk.END).strip()
            if not title or not start or not end:
                messagebox.showwarning("Input Error", "Please fill in title, start time, and end time")
                return
            dialog.destroy()
            t = threading.Thread(target=self._edit_calendar_event_worker, args=(event_id, title, start, end, description))
            t.daemon = True
            t.start()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Save", command=update_event).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

    def _edit_calendar_event_worker(self, event_id, title, start, end, description):
        """Edit calendar event in background thread"""
        self._log("Updating calendar event...")
        try:
            updates = {
                'summary': title,
                'start': {'dateTime': start, 'timeZone': 'UTC'},
                'end': {'dateTime': end, 'timeZone': 'UTC'},
                'description': description
            }
            updated_id = self.gcal.update_event(event_id, updates)
            if updated_id:
                self._log("Calendar event updated")
                messagebox.showinfo("Success", "Calendar event updated successfully")
                self.after(1000, self._calendar_refresh)
            else:
                messagebox.showerror("Error", "Failed to update event")
        except Exception as exc:
            self._log("Update calendar event error:", exc)
            messagebox.showerror("Update Error", str(exc))

    def _on_delete_calendar_event(self, parent_window, calendar_listbox):
        """Delete selected calendar event"""
        sel = calendar_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select an event first")
            return
        
        if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this event?"):
            return
        
        idx = sel[0]
        if not hasattr(parent_window, 'calendar_events'):
            messagebox.showerror("Error", "Unable to get event list")
            return
        
        event = parent_window.calendar_events[idx]
        event_id = event.get('id')
        
        t = threading.Thread(target=self._delete_calendar_event_worker, args=(event_id,))
        t.daemon = True
        t.start()

    def _delete_calendar_event_worker(self, event_id):
        """Delete calendar event in background thread"""
        self._log("Deleting calendar event...")
        try:
            success = self.gcal.delete_event(event_id)
            if success:
                self._log("Calendar event deleted")
                messagebox.showinfo("Success", "Calendar event deleted successfully")
                self.after(1000, self._calendar_refresh)
            else:
                messagebox.showerror("Error", "Failed to delete event")
        except Exception as exc:
            self._log("Delete calendar event error:", exc)
            messagebox.showerror("Delete Error", str(exc))

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
