"""RecordGuard modern unified UI.

Shared left navigation, role-aware workspaces, prescription scan assistance,
health-data export/share tools, and evidence-first presentation.
Prototype only; not a diagnostic or prescribing system.
"""

import csv
import json
import os
import re
import shutil
import tempfile
import zipfile
import threading
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from functions import (
    RecordGuardError, authenticate_user, register_patient, list_all_patients,
    add_medication_record, get_medication_records_for_patient, set_medication_status,
    edit_medication_record, archive_medication_record, get_audit_log_for_record,
    recover_archived_medication_record, admin_delete_medication_record,
    recover_admin_deleted_medication_record, permanently_delete_medication_record,
    get_audit_log, create_new_user, list_users, get_patient_by_id,
    get_patient_access_history, create_record_shares_batch, list_record_shares, revoke_record_share,
    access_shared_record, request_record_correction, get_correction_requests, review_correction_request, can_add_records, can_edit_records,
    can_archive_records, can_recover_archived_records,
    can_recover_admin_deleted_records, can_admin_delete_records,
    can_permanently_delete, can_register_patients,
    create_encounter, list_encounters, add_prescription, list_prescriptions,
    add_attachment, list_attachments, archive_ehr_item, recover_archived_ehr_item,
    admin_delete_ehr_item, recover_admin_deleted_ehr_item, permanently_delete_ehr_item,
    medicine_intelligence, add_personal_medication, list_personal_medications,
    has_owner_account, create_initial_owner, create_public_user_account,
    request_patient_link, review_patient_link_request, list_patient_link_requests, unlink_patient_account,
    create_family_relationship, list_family_relationships, change_family_relationship, remove_family_relationship,
    grant_family_access, revoke_family_access, list_family_access, reset_user_password,
    backup_database, restore_database, get_backup_history,
)
from integration import patient_to_bundle
from database import get_connection
from validation import (
    validate_name, validate_age, validate_sex, validate_patient_id_format,
    validate_medicine_name, validate_response_type, validate_severity,
)

try:
    from PIL import Image
except Exception:
    Image = None
try:
    import pytesseract
except Exception:
    pytesseract = None
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    REPORTLAB = True
except Exception:
    REPORTLAB = False

APP_TITLE = "RecordGuard"
RESPONSE_TYPES = ["Effective", "Ineffective", "Allergy", "Adverse reaction", "Unknown"]
SEVERITY_LEVELS = ["", "Mild", "Moderate", "Severe"]

COLORS = {
    # Lightweight clinical theme: same navigation/workspace geometry as the
    # polished UI, with simpler surfaces and restrained contrast.
    "bg": "#F4F6F8", "surface": "#FFFFFF", "ink": "#202733", "muted": "#667085",
    "indigo": "#4656A8", "indigo_dark": "#34427F", "indigo_soft": "#EEF1FA",
    "teal": "#177E72", "teal_soft": "#EAF6F3", "purple": "#6B4FA1", "purple_soft": "#F1ECF7",
    "green": "#2E7D5B", "green_soft": "#EAF5EF", "amber": "#9A6A16", "amber_soft": "#FBF3DF",
    "red": "#B83A3A", "red_soft": "#FBECEC", "blue": "#3568B8", "blue_soft": "#EAF1FA",
    "gray": "#6B7280", "gray_soft": "#EEF0F2", "line": "#D9DEE7",
    "nav": "#E9EDF3", "nav_hover": "#DCE2EB", "nav_muted": "#687386",
}


class RecordGuardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1320x820")
        self.minsize(1050, 700)
        self.current_user = None
        self._route_history = []
        self._current_route = None
        self._nav_buttons = {}
        self._workspace = None
        self._top_title = None
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._style()
        # First-run setup is a startup state, not an optional link.  Render
        # the sign-in screen first so Tk has a real mapped parent window, then
        # open the Owner setup after the event loop becomes idle.  This also
        # makes setup reliably visible on Windows when launched with
        # `python main.py`.
        self._show_login()
        self.after_idle(self._check_first_run_owner_setup)

    def _check_first_run_owner_setup(self):
        """Open mandatory first-time Owner setup on a fresh installation."""
        try:
            owner_exists = has_owner_account()
        except Exception as exc:
            # A fresh install must not silently fall through to sign-in when
            # the owner check fails.  Surface the problem and keep a visible
            # setup action available.
            self._show_login(owner_check_error=str(exc))
            return
        if not owner_exists:
            self._first_run_setup()

    def _style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        base = ("Segoe UI", 10)
        s.configure("TFrame", background=COLORS["bg"])
        s.configure("TLabel", background=COLORS["bg"], foreground=COLORS["ink"], font=base)
        s.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["ink"], font=("Segoe UI", 22, "bold"))
        s.configure("Heading.TLabel", background=COLORS["bg"], foreground=COLORS["ink"], font=("Segoe UI", 15, "bold"))
        s.configure("Section.TLabel", background=COLORS["bg"], foreground=COLORS["ink"], font=("Segoe UI", 12, "bold"))
        s.configure("Subtitle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=("Segoe UI", 10))
        s.configure("Soft.TFrame", background=COLORS["indigo_soft"])
        s.configure("Soft.TLabel", background=COLORS["indigo_soft"], foreground=COLORS["indigo_dark"], font=("Segoe UI", 9, "bold"))
        s.configure("Card.TFrame", background=COLORS["surface"], borderwidth=1, relief="solid")
        s.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(12, 8))
        s.configure("Accent.TButton", background=COLORS["indigo"], foreground="white", font=("Segoe UI", 10, "bold"), padding=(13, 8), borderwidth=0)
        s.map("Accent.TButton", background=[("active", COLORS["indigo_dark"]), ("disabled", "#AEB6D8")])
        s.configure("Ghost.TButton", background=COLORS["indigo_soft"], foreground=COLORS["indigo_dark"], font=("Segoe UI", 10, "bold"), padding=(12, 8), borderwidth=0)
        s.map("Ghost.TButton", background=[("active", COLORS["nav_hover"])])
        s.configure("Treeview", background="white", fieldbackground="white", foreground=COLORS["ink"], rowheight=34, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", background=COLORS["gray_soft"], foreground=COLORS["ink"], font=("Segoe UI", 9, "bold"), padding=8)
        s.map("Treeview", background=[("selected", COLORS["indigo_soft"])], foreground=[("selected", COLORS["indigo_dark"])])
        s.configure("TEntry", padding=7, font=("Segoe UI", 10))
        s.configure("Error.TEntry", padding=7, font=("Segoe UI", 10), fieldbackground=COLORS["red_soft"], bordercolor=COLORS["red"], lightcolor=COLORS["red"], darkcolor=COLORS["red"])
        s.configure("TCombobox", padding=7, font=("Segoe UI", 10))
        s.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        s.configure("TNotebook.Tab", padding=(13, 8), font=("Segoe UI", 10, "bold"))

    def _status(self, message, kind="info", parent=None, timeout=4500):
        """Show a non-blocking status banner for routine feedback."""
        parent = parent or getattr(self, "_workspace", None) or self
        old = getattr(parent, "_rg_status", None)
        if old is not None and old.winfo_exists():
            old.destroy()
        palette = {
            "success": (COLORS["green_soft"], COLORS["green"]),
            "warning": (COLORS["amber_soft"], COLORS["amber"]),
            "error": (COLORS["red_soft"], COLORS["red"]),
            "info": (COLORS["blue_soft"], COLORS["blue"]),
        }
        bg, fg = palette.get(kind, palette["info"])
        banner = tk.Frame(parent, bg=bg, highlightbackground=COLORS["line"], highlightthickness=1)
        banner.pack(fill="x", padx=34 if parent is getattr(self, "_workspace", None) else 12, pady=(8, 2))
        tk.Label(banner, text=str(message), bg=bg, fg=fg, font=("Segoe UI", 9, "bold"), anchor="w", wraplength=950, justify="left").pack(fill="x", padx=12, pady=9)
        parent._rg_status = banner
        if timeout:
            banner.after(timeout, lambda: banner.destroy() if banner.winfo_exists() else None)
        return banner

    def _field_validator(self, entry, validator, error_label):
        def check(_event=None):
            try:
                err = validator(entry.get())
            except TypeError:
                err = None
            error_label.config(text=err or "")
            try:
                entry.configure(style="Error.TEntry" if err else "TEntry")
            except tk.TclError:
                pass
            return err
        entry.bind("<FocusOut>", check, add="+")
        entry.bind("<KeyRelease>", lambda _e: check(), add="+")
        return check

    def _add_field(self, parent, row, label, key, validator=None, width=44, show=None):
        tk.Label(parent, text=label, bg="white", fg="#52586A", font=("Segoe UI", 8, "bold")).grid(row=row, column=0, sticky="nw", padx=16, pady=(7, 2))
        entry = ttk.Entry(parent, width=width, show=show or "")
        entry.grid(row=row, column=1, sticky="ew", padx=16, pady=(7, 0))
        err = tk.Label(parent, text="", bg="white", fg=COLORS["red"], font=("Segoe UI", 8), anchor="w")
        err.grid(row=row + 1, column=1, sticky="w", padx=16, pady=(0, 4))
        if validator:
            self._field_validator(entry, validator, err)
        return entry, err

    def _tree_empty(self, parent, tree, message):
        if tree.get_children():
            return None
        holder = getattr(parent, "_rg_empty_state", None)
        if holder is not None and holder.winfo_exists():
            holder.destroy()
        holder = tk.Frame(parent, bg="white")
        holder.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(holder, text="Nothing here yet", bg="white", fg=COLORS["ink"], font=("Segoe UI", 11, "bold")).pack(pady=(8, 2))
        tk.Label(holder, text=message, bg="white", fg=COLORS["muted"], font=("Segoe UI", 9), justify="center", wraplength=420).pack(padx=18, pady=(0, 10))
        parent._rg_empty_state = holder
        return holder

    def _tree_tags(self, tree):
        tree.tag_configure("active", foreground=COLORS["ink"], background=COLORS["surface"])
        tree.tag_configure("archived", foreground=COLORS["gray"], background=COLORS["gray_soft"])
        tree.tag_configure("admin_deleted", foreground=COLORS["red"], background=COLORS["red_soft"])
        tree.tag_configure("zebra", background="#FAFBFD")

    def _role(self): return self.current_user.get("role") if self.current_user else None
    def _is_patient(self): return self._role() == "patient"

    def _clear(self):
        for w in self.winfo_children(): w.destroy()
        self._workspace = None; self._nav_buttons = {}; self._top_title = None
        self.configure(bg=COLORS["bg"])

    def _show_login(self, owner_check_error=None):
        self._clear(); self.title("RecordGuard — Sign in")
        root = tk.Frame(self, bg=COLORS["bg"]); root.pack(fill="both", expand=True)
        # Same two-column placement as the polished project, intentionally
        # lighter for rapid functional testing.
        left = tk.Frame(root, bg=COLORS["indigo"], width=380); left.pack(side="left", fill="y"); left.pack_propagate(False)
        tk.Label(left, text="RECORDGUARD", bg=COLORS["indigo"], fg="white", font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=36, pady=(42, 16))
        tk.Label(left, text="Your health.\nYour records.\nYour control.", bg=COLORS["indigo"], fg="white", font=("Segoe UI", 25, "bold"), justify="left").pack(anchor="w", padx=36)
        tk.Label(left, text="A secure workspace for documented health information,\nsharing, evidence and governance.", bg=COLORS["indigo"], fg="#E4E8F8", font=("Segoe UI", 10), justify="left").pack(anchor="w", padx=36, pady=(18, 0))
        tk.Label(left, text="LIGHTWEIGHT FUNCTIONAL TEST BUILD", bg=COLORS["indigo"], fg="#D9DEF1", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=36, pady=(40, 0))

        panel = tk.Frame(root, bg=COLORS["bg"]); panel.pack(side="left", fill="both", expand=True)
        box = tk.Frame(panel, bg="white", highlightbackground=COLORS["line"], highlightthickness=1); box.place(relx=.5, rely=.5, anchor="center", relwidth=.64, relheight=.58)
        tk.Label(box, text="Welcome back", bg="white", fg=COLORS["ink"], font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=40, pady=(38, 4))
        tk.Label(box, text="Sign in to your secure health workspace.", bg="white", fg=COLORS["muted"], font=("Segoe UI", 10)).pack(anchor="w", padx=40, pady=(0, 24))
        form = tk.Frame(box, bg="white"); form.pack(fill="x", padx=40)
        tk.Label(form, text="USERNAME OR EMAIL", bg="white", fg="#52586A", font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))
        u = ttk.Entry(form); u.pack(fill="x", ipady=4, pady=(0, 15))
        tk.Label(form, text="PASSWORD", bg="white", fg="#52586A", font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))
        p = ttk.Entry(form, show="*"); p.pack(fill="x", ipady=4)
        show_pw=tk.BooleanVar(value=False)
        ttk.Checkbutton(form,text="Show password",variable=show_pw,command=lambda:p.configure(show="" if show_pw.get() else "*")).pack(anchor="w",pady=(5,0))
        err = tk.Label(form, text="", bg="white", fg=COLORS["red"], font=("Segoe UI", 9), wraplength=430, justify="left"); err.pack(anchor="w", pady=(8, 2))
        def login():
            try:
                self.current_user = authenticate_user(u.get().strip(), p.get())
                self._build_shell("Home")
            except Exception as exc:
                err.config(text=str(exc))
        ttk.Button(form, text="Sign in", style="Accent.TButton", command=login).pack(fill="x", pady=(8, 8))
        ttk.Button(form, text="Forgot password?", style="Ghost.TButton", command=self._account_recovery).pack(fill="x", pady=(0, 8))
        ttk.Button(form, text="Help / Support", style="Ghost.TButton", command=self._support).pack(fill="x", pady=(0, 8))
        try:
            owner_exists = has_owner_account()
        except Exception:
            owner_exists = True
        if not owner_exists or owner_check_error:
            setup_text = "First-time setup — Create Owner account"
            ttk.Button(form, text=setup_text, style="Accent.TButton", command=self._first_run_setup).pack(fill="x", pady=(0, 8))
            tk.Label(
                form,
                text=("Owner setup is required before anyone can sign in." if not owner_check_error
                      else "Owner setup could not be checked. Open setup or review startup_log.txt."),
                bg="white", fg=COLORS["amber"], font=("Segoe UI", 8, "bold"),
                wraplength=430, justify="left"
            ).pack(anchor="w", pady=(0, 8))
        ttk.Button(form, text="Create an account", style="Ghost.TButton", command=self._public_user_signup).pack(fill="x", pady=(0, 8))
        ttk.Button(form, text="Exit", command=self.destroy).pack(fill="x")
        tk.Label(box, text="Functional test build — core workflows use the same RecordGuard backend.", bg="white", fg="#8A91A3", font=("Segoe UI", 8), wraplength=430, justify="left").pack(anchor="w", padx=40, pady=(18, 0))
        u.bind("<Return>", lambda e: p.focus_set()); p.bind("<Return>", lambda e: login()); u.focus_set()

    def _account_recovery(self):
        messagebox.showinfo("Account recovery", "For this prototype, password recovery is handled by an authorized RecordGuard administrator/Owner. No password or recovery secret is shown on the sign-in screen.", parent=self)

    def _support(self):
        messagebox.showinfo("RecordGuard support", "Use the Owner/Admin of your RecordGuard organization for account, Patient-linking, or access issues.", parent=self)

    def _public_user_signup(self):
        w=tk.Toplevel(self); w.title("RecordGuard — Create account"); w.geometry("560x420"); w.transient(self); w.grab_set()
        c=tk.Frame(w,bg=COLORS["bg"],padx=26,pady=22); c.pack(fill="both",expand=True)
        tk.Label(c,text="Create a RecordGuard account",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",20,"bold")).pack(anchor="w")
        tk.Label(c,text="Self-registration creates only a login account. It does not create a patient profile or grant access to medical records. If an authorized organization user has already registered your patient profile, your account can be linked to that Patient ID through the authorized workflow.",bg=COLORS["bg"],fg=COLORS["muted"],font=("Segoe UI",9),wraplength=500,justify="left").pack(anchor="w",pady=(5,16))
        f=tk.Frame(c,bg="white",highlightbackground=COLORS["line"],highlightthickness=1,padx=20,pady=16); f.pack(fill="both",expand=True)
        fields={}
        for i,(lab,key,show) in enumerate((("Full name","name",""),("Username","username",""),("Email (optional)","email",""),("Password","password","*"),("Confirm password","confirm","*"))):
            tk.Label(f,text=lab,bg="white",fg=COLORS["ink"],font=("Segoe UI",9,"bold")).grid(row=i,column=0,sticky="w",padx=8,pady=7)
            e=ttk.Entry(f,width=36,show=show); e.grid(row=i,column=1,sticky="ew",padx=8,pady=7,ipady=2); fields[key]=e
        f.columnconfigure(1,weight=1)
        err=tk.Label(c,text="",bg=COLORS["bg"],fg=COLORS["red"],font=("Segoe UI",9),wraplength=500,justify="left"); err.pack(anchor="w",pady=(10,5))
        def create():
            if fields["password"].get()!=fields["confirm"].get(): err.config(text="Passwords do not match."); return
            try:
                create_public_user_account(fields["username"].get(),fields["password"].get(),fields["name"].get(),fields["email"].get())
                w.destroy(); self._show_login()
            except Exception as exc: err.config(text="●  "+str(exc))
        ttk.Button(c,text="Create account",style="Accent.TButton",command=create).pack(fill="x",pady=(4,6),ipady=4)
        ttk.Button(c,text="Cancel",command=w.destroy).pack(anchor="w")

    def _first_run_setup(self):
        # Prevent duplicate setup windows if the user clicks the visible
        # setup button while the automatic first-run callback is pending.
        existing = getattr(self, "_owner_setup_window", None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify(); existing.lift(); existing.focus_force()
            return

        w=tk.Toplevel(self)
        self._owner_setup_window = w
        w.title("RecordGuard — First-time Owner setup")
        w.geometry("600x620+{}+{}".format(
            max(0, (self.winfo_screenwidth()-600)//2),
            max(0, (self.winfo_screenheight()-620)//2)
        ))
        w.minsize(560,600); w.transient(self); w.protocol("WM_DELETE_WINDOW", w.destroy)
        w.lift(); w.focus_force(); w.grab_set()
        f=tk.Frame(w,bg="white",padx=28,pady=24); f.pack(fill="both",expand=True)
        tk.Label(f,text="Secure your RecordGuard workspace",bg="white",fg=COLORS["ink"],font=("Segoe UI",20,"bold")).pack(anchor="w")
        tk.Label(f,text="Create the first Owner account. No default password is created.",bg="white",fg=COLORS["muted"],font=("Segoe UI",9),wraplength=430,justify="left").pack(anchor="w",pady=(5,18))
        fields={}
        for label,key,show in [("Full name","name",None),("Username","username",None),("Owner password","password","*"),("Confirm password","confirm","*")]:
            tk.Label(f,text=label,bg="white",fg="#52586A",font=("Segoe UI",8,"bold")).pack(anchor="w",pady=(5,5)); e=ttk.Entry(f,width=48,show=show) if show else ttk.Entry(f,width=48); e.pack(fill="x",ipady=4); fields[key]=e
        err=tk.Label(f,text="",bg="white",fg=COLORS["red"],font=("Segoe UI",8)); err.pack(anchor="w",pady=7)
        def create():
            if fields["password"].get()!=fields["confirm"].get(): err.config(text="Passwords do not match."); return
            try:
                user=create_initial_owner(fields["username"].get(),fields["password"].get(),fields["name"].get())
                w.destroy(); self.current_user=user; self._build_shell("Home")
            except Exception as exc: err.config(text="●  "+str(exc))
        ttk.Button(f,text="Create Owner account",style="Accent.TButton",command=create).pack(fill="x",pady=(10,6),ipady=4)
        fields["confirm"].bind("<Return>",lambda e:create())
        ttk.Button(f,text="Cancel",command=w.destroy).pack(anchor="w",pady=6)
        w.bind("<Destroy>", lambda e: setattr(self, "_owner_setup_window", None) if e.widget is w else None)

    def _open_shared_link(self):
        from tkinter import simpledialog
        token=simpledialog.askstring("Secure shared record","Paste the RecordGuard share token:",parent=self)
        if not token:return
        try:
            result=access_shared_record(token)
            sh=result["share"]; rec=result["record"]; w=tk.Toplevel(self); w.title("RecordGuard — Shared Health Record"); w.geometry("700x500"); f=tk.Frame(w,bg=COLORS["bg"],padx=22,pady=20); f.pack(fill="both",expand=True)
            tk.Label(f,text="🛡 Shared securely through RecordGuard",bg=COLORS["teal_soft"],fg=COLORS["teal"],font=("Segoe UI",12,"bold"),padx=12,pady=9).pack(fill="x")
            tk.Label(f,text=f"Shared by: {sh.get('shared_by')}  ·  Recipient: {sh.get('shared_with')}",bg=COLORS["bg"],fg=COLORS["muted"],font=("Segoe UI",9)).pack(anchor="w",pady=(15,4))
            tk.Label(f,text=f"Resource: {(sh.get('resource_type') or 'medication').title()}",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",20,"bold")).pack(anchor="w",pady=8)
            resource_type = (sh.get("resource_type") or "medication").lower()
            allowed_fields = {
                "medication": {"medicine_name", "response_type", "reaction", "severity", "reason", "notes", "record_date"},
                "encounter": {"visit_date", "visit_type", "chief_complaint", "diagnosis", "notes"},
                "prescription": {"medicine_name", "dosage", "frequency", "duration", "instructions", "created_at"},
                "document": {"original_name", "mime_type", "uploaded_at"},
            }.get(resource_type, {"original_name", "mime_type"})
            for k,v in rec.items():
                if k not in allowed_fields or v in (None, ""): continue
                tk.Label(f,text=f"{k.replace('_',' ').title()}: {v}",bg="white",fg=COLORS["ink"],anchor="w",padx=12,pady=5).pack(fill="x",pady=1)
            tk.Label(f,text="This view contains only the resource authorized by this share. Access is audited and the share may expire or be revoked.",bg=COLORS["teal_soft"],fg="#54716D",font=("Segoe UI",8),wraplength=620,justify="left",padx=10,pady=9).pack(fill="x",pady=12)
        except Exception as exc: self._status(str(exc),"error")

    def _logout(self):
        if messagebox.askyesno("Sign out","Sign out of RecordGuard?",parent=self): self.current_user=None; self._show_login()

    # --------------------------- shell/navigation ---------------------------
    def _run_background(self, task, on_success, on_error, title="Working…"):
        """Run non-UI work off the Tkinter event loop.

        Worker threads must never touch Tk widgets. Completion/error callbacks
        are marshalled back to the Tk event loop with after().
        """
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("390x145")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frame = tk.Frame(dialog, bg="white", padx=24, pady=20)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=title, bg="white", fg=COLORS["ink"],
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(frame, text="RecordGuard is working. Please wait…",
                 bg="white", fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 12))
        progress = ttk.Progressbar(frame, mode="indeterminate", length=335)
        progress.pack(fill="x")
        progress.start(10)

        finished = {"value": False}

        def finish(callback, value=None):
            if finished["value"]:
                return
            finished["value"] = True
            try:
                progress.stop()
                if dialog.winfo_exists():
                    dialog.grab_release()
                    dialog.destroy()
            finally:
                if value is None:
                    callback()
                else:
                    callback(value)

        def worker():
            try:
                result = task()
            except Exception as exc:
                self.after(0, lambda exc=exc: finish(on_error, exc))
            else:
                self.after(0, lambda result=result: finish(on_success, result))

        threading.Thread(target=worker, daemon=True, name="RecordGuardWorker").start()

    def _nav_items(self):
        r=self._role()
        if r=="patient":
            return [("HM","Home","_home"),("HL","My Health","_personal_health"),("SP","Safety Passport","_passport"),("FM","Family Access","_family"),("PS","Privacy & Sharing","_privacy"),("NT","Notifications","_notifications")]
        if r=="doctor":
            return [("HM","Workspace","_home"),("PT","Patients","_patients"),("CR","Clinical Records","_ehr"),("TM","Treatment Memory","_treatment"),("PS","Privacy & Sharing","_privacy"),("NT","Notifications","_notifications")]
        if r=="staff":
            return [("HM","Workspace","_home"),("PT","Patients","_patients"),("CR","Clinical Records","_ehr"),("TV","Tasks / Verification","_tasks"),("NT","Notifications","_notifications")]
        if r=="admin":
            return [("HM","Operations","_home"),("PP","People & Patients","_people"),("CR","Records","_records"),("FM","Family Access","_family"),("PS","Privacy & Security","_privacy"),("NT","Notifications","_notifications")]
        if r=="owner":
            return [("HM","Governance","_home"),("OR","Organization","_organization"),("CR","Records","_records"),("FM","Family Access","_family"),("SC","Security & Privacy","_privacy"),("IN","Interoperability","_interop"),("BK","Backup & Restore","_backup"),("NT","Notifications","_notifications")]
        return [("HM","Home","_home"),("NT","Notifications","_notifications")]

    def _build_shell(self, initial="Home"):
        self._clear(); self.title(f"RecordGuard — {self._role().title()}")
        root=tk.Frame(self,bg=COLORS["bg"]); root.pack(fill="both",expand=True)
        side=tk.Frame(root,bg=COLORS["nav"],width=236); side.pack(side="left",fill="y"); side.pack_propagate(False)
        brand=tk.Frame(side,bg=COLORS["nav"]); brand.pack(fill="x",padx=20,pady=(22,22)); tk.Label(brand,text="RG",bg=COLORS["nav"],fg="white",font=("Segoe UI",19,"bold")).pack(side="left"); tk.Label(brand,text="RecordGuard",bg=COLORS["nav"],fg="#E7E9FF",font=("Segoe UI",12,"bold")).pack(side="left",padx=10)
        tk.Label(side,text=("PERSONAL HEALTH" if self._is_patient() else f"{self._role().upper()} WORKSPACE"),bg=COLORS["nav"],fg="#9097B8",font=("Segoe UI",7,"bold")).pack(anchor="w",padx=22,pady=(0,8))
        nav=tk.Frame(side,bg=COLORS["nav"]); nav.pack(fill="both",expand=True,padx=11)
        self._nav_buttons={}
        for icon,label,key in self._nav_items():
            b=tk.Button(nav,text=f"{icon}   {label}",command=lambda k=key:self._route(k),bd=0,anchor="w",bg=COLORS["nav"],fg="#D6D9E8",activebackground=COLORS["nav_hover"],activeforeground="white",font=("Segoe UI",10,"bold"),cursor="hand2",padx=15,pady=11)
            b.pack(fill="x",pady=2); self._nav_buttons[key]=b
        bottom=tk.Frame(side,bg=COLORS["nav"]); bottom.pack(side="bottom",fill="x",padx=12,pady=15)
        name=self.current_user.get("full_name") or self.current_user.get("username") or "User"
        tk.Label(bottom,text=name,bg=COLORS["nav"],fg="white",font=("Segoe UI",9,"bold")).pack(anchor="w",padx=10); tk.Label(bottom,text=self._role().title(),bg=COLORS["nav"],fg="#9097B8",font=("Segoe UI",8)).pack(anchor="w",padx=10,pady=(2,8))
        tk.Button(bottom,text="PR  Profile",command=lambda:self._route("_profile"),bd=0,bg=COLORS["nav"],fg="#C8CCE0",activebackground=COLORS["nav"],activeforeground="white",anchor="w",font=("Segoe UI",9,"bold"),cursor="hand2",padx=10,pady=7).pack(fill="x")
        tk.Button(bottom,text="ST  Settings",command=lambda:self._route("_settings"),bd=0,bg=COLORS["nav"],fg="#C8CCE0",activebackground=COLORS["nav"],activeforeground="white",anchor="w",font=("Segoe UI",9,"bold"),cursor="hand2",padx=10,pady=7).pack(fill="x")
        tk.Button(bottom,text="SO  Sign out",command=self._logout,bd=0,bg=COLORS["nav"],fg="#C8CCE0",activebackground=COLORS["nav"],activeforeground="white",anchor="w",font=("Segoe UI",9,"bold"),cursor="hand2",padx=10,pady=7).pack(fill="x")
        main=tk.Frame(root,bg=COLORS["bg"]); main.pack(side="left",fill="both",expand=True)
        top=tk.Frame(main,bg="white",height=68,highlightbackground=COLORS["line"],highlightthickness=1); top.pack(fill="x"); top.pack_propagate(False)
        self._top_title=tk.Label(top,text="Home",bg="white",fg=COLORS["ink"],font=("Segoe UI",15,"bold")); self._top_title.pack(side="left",padx=28)
        search=tk.Frame(top,bg="#F3F4F7",highlightbackground=COLORS["line"],highlightthickness=1); search.pack(side="left",fill="x",expand=True,padx=20,pady=14); tk.Label(search,text="⌕",bg="#F3F4F7",fg="#98A2B3",font=("Segoe UI",13)).pack(side="left",padx=(12,5)); self._global_search=ttk.Entry(search); self._global_search.insert(0,""); self._global_search.pack(side="left",fill="x",expand=True,padx=5,ipady=3); self._global_search.bind("<Return>",lambda e:self._run_global_search(self._global_search.get()))
        self.bind_all("<Control-f>", lambda e: (self._global_search.focus_set(), "break")[1])
        self.bind_all("<Escape>", lambda e: (self.focus_set(), "break")[1])
        self.bind_all("<Control-n>", lambda e: (self._route("_register") if self._role() in {"owner","admin","doctor","staff"} else None, "break")[1])
        if self._role() in {"owner","admin","doctor","staff"}:
            ttk.Button(top,text="＋ Create",style="Ghost.TButton",command=self._open_creation_hub).pack(side="right",padx=(6,12),pady=13)
        prot=tk.Frame(top,bg=COLORS["teal_soft"]); prot.pack(side="right",padx=12,pady=15); tk.Label(prot,text="●  PROTECTED",bg=COLORS["teal_soft"],fg=COLORS["teal"],font=("Segoe UI",8,"bold")).pack(padx=12,pady=6)
        self._workspace=tk.Frame(main,bg=COLORS["bg"]); self._workspace.pack(fill="both",expand=True)
        self._route("_home" if initial=="Home" else initial)

    def _route(self,key, _from_back=False):
        """Navigate between workspace pages while keeping a small back stack."""
        if not _from_back and getattr(self, "_current_route", None) and self._current_route != key:
            self._route_history.append(self._current_route)
            # Prevent an unbounded stack from growing during normal use.
            self._route_history = self._route_history[-20:]
        self._current_route = key
        if key=="_home": self._render_home()
        elif key=="_personal_health": self._render_personal_health()
        elif key=="_notifications": self._render_notifications()
        elif key=="_tasks": self._render_tasks()
        elif key=="_people": self._render_people_hub()
        elif key=="_records": self._render_records_hub()
        elif key=="_organization": self._render_organization_hub()
        elif key=="_interop": self._render_interop()
        elif key=="_medicines": self._render_medicines()
        elif key=="_treatment": self._render_treatment()
        elif key=="_timeline": self._render_timeline()
        elif key=="_family": self._render_family()
        elif key=="_passport": self._render_passport()
        elif key=="_privacy": self._render_privacy()
        elif key=="_access": self._render_access()
        elif key=="_share_export": self._render_share_export()
        elif key=="_patients": self._render_patients()
        elif key=="_register": self._show_register()
        elif key=="_ehr": self._show_ehr()
        elif key=="_add_medication": self._show_add_medication()
        elif key=="_history": self._show_history()
        elif key=="_users": self._show_users()
        elif key=="_security": self._show_security()
        elif key=="_audit": self._show_audit_log()
        elif key=="_backup": self._show_backup()
        elif key=="_profile": self._show_profile()
        elif key=="_settings": self._show_settings()
        self._mark_active(key)

    def _go_back(self):
        """Return to the previous workspace page, or role home if none exists."""
        if getattr(self, "_route_history", None):
            previous = self._route_history.pop()
            self._route(previous, _from_back=True)
            return
        self._route("_home", _from_back=True)

    def _mark_active(self,key):
        for k,b in self._nav_buttons.items(): b.config(bg=COLORS["indigo"] if k==key else COLORS["nav"],fg="white" if k==key else "#D6D9E8")

    def _run_global_search(self,q):
        q=str(q or "").strip().lower()
        if not q:
            return
        try:
            if self._is_patient():
                pid=self._patient_id(); records=self._records(pid); people=[]
            else:
                people=list_all_patients(self.current_user); records=[]
                for person in people[:100]:
                    records.extend(self._records(person.get("patient_id")))
            matches=[p for p in people if q in str(p.get("patient_id","")).lower() or q in str(p.get("name","")).lower() or q in str(p.get("phone_number","")).lower()]
            med=[r for r in records if q in str(r.get("medicine_name","")).lower() or q in str(r.get("response_type","")).lower()]
            w=tk.Toplevel(self); w.title("RecordGuard Search"); w.geometry("760x520"); f=tk.Frame(w,bg=COLORS["bg"],padx=20,pady=18); f.pack(fill="both",expand=True)
            tk.Label(f,text=f"Search results for ‘{q}’",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",20,"bold")).pack(anchor="w")
            if matches:
                tk.Label(f,text="Patients",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",10,"bold")).pack(anchor="w",pady=(14,5))
                for x in matches[:20]: ttk.Button(f,text=f"{x.get('patient_id')}  ·  {x.get('name')}",command=lambda pid=x.get('patient_id'): (w.destroy(),self._open_patient(pid))).pack(fill="x",pady=2)
            if med:
                tk.Label(f,text="Medication records",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",10,"bold")).pack(anchor="w",pady=(14,5))
                for x in med[:20]: tk.Label(f,text=f"{x.get('medicine_name')}  ·  {x.get('response_type')}  ·  {x.get('record_date','')}",bg="white",fg=COLORS["ink"],anchor="w",padx=10,pady=7).pack(fill="x",pady=2)
            if not matches and not med: tk.Label(f,text="No authorized results found.",bg=COLORS["bg"],fg=COLORS["muted"]).pack(anchor="w",pady=20)
        except Exception as exc: self._status(str(exc),"error")

    def _render_people_hub(self):
        c=self._page("People & Patients","Manage people and open patient workspaces within your organization.")
        quick=self._card(c,COLORS["indigo_soft"])
        tk.Label(quick,text="Quick actions",bg=COLORS["indigo_soft"],fg=COLORS["indigo_dark"],font=("Segoe UI",13,"bold")).pack(anchor="w",padx=18,pady=(14,6))
        actions=tk.Frame(quick,bg=COLORS["indigo_soft"]); actions.pack(fill="x",padx=18,pady=(0,14))
        ttk.Button(actions,text="＋ Create person / account",style="Accent.TButton",command=self._open_creation_hub).pack(side="left")
        for title,desc,key in [("Users","Create and review organization user accounts. Doctors, staff, and patient login accounts are created here.","_users"),("Patients","Search and open patient records.","_patients")]:
            f=self._card(c); tk.Label(f,text=title,bg="white",fg=COLORS["ink"],font=("Segoe UI",13,"bold")).pack(anchor="w",padx=18,pady=(14,3)); tk.Label(f,text=desc,bg="white",fg=COLORS["muted"],font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=(0,8)); ttk.Button(f,text="Open →",style="Accent.TButton",command=lambda k=key:self._route(k)).pack(anchor="w",padx=18,pady=(0,14))
    def _render_records_hub(self):
        c=self._page("Records","Clinical records, lifecycle controls and correction workflows.")
        links=[("Clinical Records","Encounters, prescriptions and documents.","_ehr"),("Record Lifecycle","Archive, recover and controlled deletion.","_security")]
        if self._role() in {"owner","admin"}: links.append(("Correction Requests","Review patient correction requests.","_security"))
        for title,desc,key in links:
            f=self._card(c); tk.Label(f,text=title,bg="white",fg=COLORS["ink"],font=("Segoe UI",13,"bold")).pack(anchor="w",padx=18,pady=(14,3)); tk.Label(f,text=desc,bg="white",fg=COLORS["muted"],font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=(0,8)); ttk.Button(f,text="Open →",style="Accent.TButton",command=lambda k=key:self._route(k)).pack(anchor="w",padx=18,pady=(0,14))
    def _render_organization_hub(self):
        c=self._page("Organization","Organization-level administration for the current RecordGuard workspace.")
        f=self._card(c); org=self.current_user.get("organization_id") or "DEFAULT"; tk.Label(f,text=f"Organization: {org}",bg="white",fg=COLORS["ink"],font=("Segoe UI",15,"bold")).pack(anchor="w",padx=18,pady=(16,4)); tk.Label(f,text="Users and patients are scoped to this organization. Cross-organization access is denied by the authorization layer.",bg="white",fg=COLORS["muted"],font=("Segoe UI",9),wraplength=850).pack(anchor="w",padx=18,pady=(0,12)); ttk.Button(f,text="Manage users",style="Accent.TButton",command=lambda:self._route("_users")).pack(anchor="w",padx=18,pady=(0,14))
    def _render_privacy_hub(self):
        c=self._page("Privacy & Security","Controlled sharing, access visibility and security controls.")
        f=self._card(c); tk.Label(f,text="Controlled data sharing",bg="white",fg=COLORS["ink"],font=("Segoe UI",13,"bold")).pack(anchor="w",padx=18,pady=(14,3)); tk.Label(f,text="Create, review and revoke time-limited data shares. Existing role and organization permissions always apply.",bg="white",fg=COLORS["muted"],font=("Segoe UI",9),wraplength=850).pack(anchor="w",padx=18,pady=(0,8)); ttk.Button(f,text="Open Sharing & Export",style="Accent.TButton",command=lambda:self._route("_share_export")).pack(anchor="w",padx=18,pady=(0,14)); ttk.Button(f,text="Open Security & Records",style="Ghost.TButton",command=lambda:self._route("_security")).pack(anchor="w",padx=18,pady=(0,14))
    def _render_notifications(self):
        c=self._page("Notifications","RecordGuard workflow and security notifications.")
        f=self._card(c,COLORS["blue_soft"]); tk.Label(f,text="Notification center is ready for workflow integration",bg=COLORS["blue_soft"],fg=COLORS["blue"],font=("Segoe UI",13,"bold")).pack(anchor="w",padx=18,pady=(16,4)); tk.Label(f,text="The current build does not yet generate persistent in-app notifications. Verification tasks, correction updates, share activity and security events remain available in their respective workspaces.",bg=COLORS["blue_soft"],fg="#4D6288",font=("Segoe UI",9),wraplength=800,justify="left").pack(anchor="w",padx=18,pady=(0,16))
    def _render_tasks(self):
        c=self._page("Tasks / Verification","Clinical workflow items that require review.")
        f=self._card(c); tk.Label(f,text="Pending clinical verification",bg="white",fg=COLORS["ink"],font=("Segoe UI",13,"bold")).pack(anchor="w",padx=18,pady=(16,6))
        try:
            patients=list_all_patients(self.current_user); count=0
            for p in patients:
                for rx in list_prescriptions(self.current_user,p["patient_id"]):
                    if "[PENDING VERIFICATION]" in str(rx.get("prescribed_by","")):
                        count+=1; tk.Label(f,text=f"{p.get('patient_id')} · {rx.get('medicine_name')} · awaiting clinician verification",bg=COLORS["amber_soft"],fg=COLORS["amber"],anchor="w",padx=12,pady=7).pack(fill="x",padx=18,pady=3)
            if not count: tk.Label(f,text="No pending verification tasks.",bg="white",fg=COLORS["muted"]).pack(anchor="w",padx=18,pady=(4,16))
        except Exception as exc: tk.Label(f,text=str(exc),bg="white",fg=COLORS["red"]).pack(anchor="w",padx=18,pady=16)
    def _render_interop(self):
        c=self._page("Interoperability","Export documented health data in interoperable formats.")
        f=self._card(c); tk.Label(f,text="FHIR-compatible export",bg="white",fg=COLORS["ink"],font=("Segoe UI",13,"bold")).pack(anchor="w",padx=18,pady=(16,4)); tk.Label(f,text="Use Privacy & Sharing → Data Export to choose records and generate an interoperable bundle.",bg="white",fg=COLORS["muted"],font=("Segoe UI",9),wraplength=800).pack(anchor="w",padx=18,pady=(0,16)); ttk.Button(f,text="Open Data Export",style="Accent.TButton",command=lambda:self._route("_share_export")).pack(anchor="w",padx=18,pady=(0,16))

    def _page(self,title,subtitle=""):
        for w in self._workspace.winfo_children(): w.destroy()
        self._top_title.config(text=title)
        outer=tk.Frame(self._workspace,bg=COLORS["bg"]); outer.pack(fill="both",expand=True)
        cv=tk.Canvas(outer,bg=COLORS["bg"],highlightthickness=0); sb=ttk.Scrollbar(outer,orient="vertical",command=cv.yview); cv.configure(yscrollcommand=sb.set); cv.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        content=tk.Frame(cv,bg=COLORS["bg"]); win=cv.create_window((0,0),window=content,anchor="nw"); content.bind("<Configure>",lambda e:cv.configure(scrollregion=cv.bbox("all"))); cv.bind("<Configure>",lambda e:cv.itemconfigure(win,width=e.width))
        def _wheel(event):
            if event.widget.winfo_toplevel() is not self:
                return
            if getattr(event, "delta", 0):
                units = -max(1, abs(int(event.delta / 120))) if event.delta > 0 else max(1, abs(int(event.delta / 120)))
            else:
                units = 1
            cv.yview_scroll(units, "units")
            return "break"
        # Replace the previous page's global wheel bindings so handlers do not stack.
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")
        self.bind_all("<MouseWheel>", _wheel)
        self.bind_all("<Button-4>", lambda e: (cv.yview_scroll(-1, "units"), "break")[1] if e.widget.winfo_toplevel() is self else None)
        self.bind_all("<Button-5>", lambda e: (cv.yview_scroll(1, "units"), "break")[1] if e.widget.winfo_toplevel() is self else None)
        head=tk.Frame(content,bg=COLORS["bg"]); head.pack(fill="x",padx=36,pady=(22,20))
        top_actions=tk.Frame(head,bg=COLORS["bg"]); top_actions.pack(fill="x",pady=(0,8))
        ttk.Button(top_actions,text="← Back",style="Ghost.TButton",command=self._go_back).pack(side="left")
        tk.Label(head,text=title,bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",26,"bold")).pack(anchor="w");
        if subtitle: tk.Label(head,text=subtitle,bg=COLORS["bg"],fg=COLORS["muted"],font=("Segoe UI",10),wraplength=950,justify="left").pack(anchor="w",pady=(5,0))
        return content

    def _card(self,parent,bg="white",pad=18):
        # Cards may contain either pack- or grid-managed children. Do not add a
        # child with pack() here, because forms place their controls with grid()
        # directly inside the card. Mixing geometry managers in one parent causes
        # Tkinter to raise TclError and can make the Register Patient screen appear
        # blank/non-functional. The border provides the visual separation without
        # introducing a competing geometry manager.
        f=tk.Frame(parent,bg=bg,highlightbackground=COLORS["line"],highlightthickness=1)
        f.pack(fill="x",pady=8)
        return f

    def _pill(self,parent,text,color,soft=None):
        soft=soft or color; return tk.Label(parent,text=text,bg=soft,fg=color,font=("Segoe UI",8,"bold"),padx=9,pady=5)

    def _patient_id(self): return self.current_user.get("patient_id") if self._is_patient() else None
    def _records(self,pid):
        try: return get_medication_records_for_patient(pid,user=self.current_user) if pid else []
        except Exception: return []

    # --------------------------- home ---------------------------
    def _render_home(self):
        if self._is_patient(): self._render_personal_home()
        else: self._render_clinical_home()

    def _render_personal_home(self):
        pid=self._patient_id(); p={}; recs=[]; enc=[]; rx=[]
        try:
            p=get_patient_by_id(self.current_user,pid) or {}; recs=self._records(pid); enc=list_encounters(self.current_user,pid); rx=list_prescriptions(self.current_user,pid)
        except Exception: pass
        name=(p.get("name") or self.current_user.get("full_name") or "there").split()[0]
        c=self._page("Home", "A calm, private view of the health information that matters to you.")
        banner=self._card(c,COLORS["teal_soft"]); tk.Label(banner,text="🛡  Your records are protected",bg=COLORS["teal_soft"],fg="#08766F",font=("Segoe UI",14,"bold")).pack(anchor="w",padx=20,pady=(16,3)); tk.Label(banner,text="You control who can access your health information. Sharing is explicit and access is logged.",bg=COLORS["teal_soft"],fg="#54716D",font=("Segoe UI",9)).pack(anchor="w",padx=20); ttk.Button(banner,text="Review privacy →",style="Ghost.TButton",command=lambda:self._route("_privacy")).pack(anchor="w",padx=20,pady=13)
        tk.Label(c,text=f"Good morning, {name}",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",22,"bold")).pack(anchor="w",padx=34,pady=(10,8))
        grid=tk.Frame(c,bg=COLORS["bg"]); grid.pack(fill="x",padx=29); [grid.columnconfigure(i,weight=1) for i in range(4)]
        stats=[("Medicines",len(rx),"prescriptions",COLORS["purple"],COLORS["purple_soft"]),("Treatment Memory",len(recs),"documented responses",COLORS["teal"],COLORS["teal_soft"]),("Health Events",len(enc),"visits & encounters",COLORS["indigo"],COLORS["indigo_soft"]),("Safety",sum(1 for r in recs if r.get("response_type") in ("Allergy","Adverse reaction")),"documented reactions",COLORS["red"],COLORS["red_soft"])]
        for i,(t,v,s,a,soft) in enumerate(stats):
            f=tk.Frame(grid,bg="white",highlightbackground=COLORS["line"],highlightthickness=1); f.grid(row=0,column=i,padx=5,sticky="nsew"); tk.Frame(f,bg=a,width=32,height=4).pack(anchor="w",padx=16,pady=(15,9)); tk.Label(f,text=t.upper(),bg="white",fg="#8A909C",font=("Segoe UI",7,"bold")).pack(anchor="w",padx=16); tk.Label(f,text=str(v),bg="white",fg=COLORS["ink"],font=("Georgia",19,"bold")).pack(anchor="w",padx=16); tk.Label(f,text=s,bg="white",fg=COLORS["muted"],font=("Segoe UI",8)).pack(anchor="w",padx=16,pady=(2,14))
        lower=tk.Frame(c,bg=COLORS["bg"]); lower.pack(fill="x",padx=34,pady=(18,28)); lower.columnconfigure(0,weight=3); lower.columnconfigure(1,weight=2)
        left=tk.Frame(lower,bg=COLORS["bg"]); left.grid(row=0,column=0,sticky="nsew",padx=(0,8)); tk.Label(left,text="What would you like to do?",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",14,"bold")).pack(anchor="w",pady=(0,7)); ag=tk.Frame(left,bg=COLORS["bg"]); ag.pack(fill="x"); ag.columnconfigure(0,weight=1); ag.columnconfigure(1,weight=1)
        actions=[("💊","Medicines","Manage prescriptions and treatment records","_medicines",COLORS["purple_soft"],COLORS["purple"]),("◷","Timeline","See your health story","_timeline",COLORS["indigo_soft"],COLORS["indigo"]),("◇","Safety Passport","Keep key safety information ready","_passport",COLORS["red_soft"],COLORS["red"]),("⇧","Share / Export","Create a health summary or data export","_share_export",COLORS["teal_soft"],COLORS["teal"])]
        for i,(ic,t,d,k,soft,a) in enumerate(actions):
            r,col=divmod(i,2); f=tk.Frame(ag,bg="white",highlightbackground=COLORS["line"],highlightthickness=1); f.grid(row=r,column=col,padx=4,pady=4,sticky="nsew"); q=tk.Frame(f,bg=soft,width=42,height=42); q.pack(anchor="w",padx=14,pady=(14,9)); q.pack_propagate(False); tk.Label(q,text=ic,bg=soft,fg=a,font=("Segoe UI",14)).pack(expand=True); tk.Label(f,text=t,bg="white",fg=COLORS["ink"],font=("Segoe UI",10,"bold")).pack(anchor="w",padx=14); tk.Label(f,text=d,bg="white",fg=COLORS["muted"],font=("Segoe UI",8),wraplength=240,justify="left").pack(anchor="w",padx=14,pady=(3,10)); tk.Button(f,text="Open →",command=lambda k=k:self._route(k),bd=0,bg="white",fg=a,activebackground="white",font=("Segoe UI",8,"bold"),cursor="hand2").pack(anchor="w",padx=14,pady=(0,13))
        right=tk.Frame(lower,bg=COLORS["bg"]); right.grid(row=0,column=1,sticky="nsew",padx=(8,0)); act=self._card(right); tk.Label(act,text="Recent activity",bg="white",fg=COLORS["ink"],font=("Segoe UI",13,"bold")).pack(anchor="w",padx=16,pady=(15,8)); events=[]
        for r in recs[:3]: events.append((r.get("record_date",""),f"{r.get('medicine_name','Medicine')} · {r.get('response_type','Response')}"))
        for e in enc[:2]: events.append((e.get("visit_date",e.get("created_at","")),e.get("visit_type") or "Clinical visit"))
        for d,t in events[:5]: tk.Label(act,text=f"•  {t}\n    {d}",bg="white",fg="#344054",font=("Segoe UI",8),justify="left").pack(anchor="w",padx=16,pady=5)
        if not events: tk.Label(act,text="Your documented activity will appear here.",bg="white",fg=COLORS["muted"],font=("Segoe UI",8)).pack(anchor="w",padx=16,pady=10)
        note=self._card(right,COLORS["purple_soft"]); tk.Label(note,text="✦ Treatment Memory",bg=COLORS["purple_soft"],fg="#4B4295",font=("Segoe UI",10,"bold")).pack(anchor="w",padx=16,pady=(13,3)); tk.Label(note,text="Evidence first. Clear context. No diagnosis or prescribing.",bg=COLORS["purple_soft"],fg="#6B668A",font=("Segoe UI",8),wraplength=270).pack(anchor="w",padx=16,pady=(0,10)); tk.Button(note,text="Explore insights →",command=lambda:self._route("_treatment"),bd=0,bg=COLORS["purple_soft"],fg=COLORS["purple"],activebackground=COLORS["purple_soft"],font=("Segoe UI",8,"bold"),cursor="hand2").pack(anchor="w",padx=16,pady=(0,14))

    def _render_clinical_home(self):
        r=self._role(); c=self._page("Workspace","Find the patient context you need, then move from glance to context to evidence.")
        hero=self._card(c,COLORS["indigo_soft"]); tk.Label(hero,text="Find a patient",bg=COLORS["indigo_soft"],fg="#302A75",font=("Segoe UI",15,"bold")).pack(anchor="w",padx=20,pady=(16,4)); tk.Label(hero,text="Search by Patient ID and open the clinical workspace.",bg=COLORS["indigo_soft"],fg="#625E86",font=("Segoe UI",9)).pack(anchor="w",padx=20); row=tk.Frame(hero,bg=COLORS["indigo_soft"]); row.pack(fill="x",padx=20,pady=13); ent=ttk.Entry(row,width=30); ent.pack(side="left",ipady=3); ttk.Button(row,text="Open patient",style="Accent.TButton",command=lambda:self._open_patient(ent.get().strip())).pack(side="left",padx=8);
        grid=tk.Frame(c,bg=COLORS["bg"]); grid.pack(fill="x",padx=29,pady=5); [grid.columnconfigure(i,weight=1) for i in range(4)]
        vals=[("ROLE",r.title(),"Access-controlled workspace",COLORS["indigo"]),("RECORDS","Active","Patient records",COLORS["teal"]),("INSIGHTS","Available","Historical evidence",COLORS["purple"]),("SECURITY","Protected","Audit trail enabled",COLORS["teal"])]
        for i,(t,v,s,a) in enumerate(vals):
            f=tk.Frame(grid,bg="white",highlightbackground=COLORS["line"],highlightthickness=1); f.grid(row=0,column=i,padx=5,sticky="nsew"); tk.Frame(f,bg=a,width=30,height=4).pack(anchor="w",padx=16,pady=(15,9)); tk.Label(f,text=t,bg="white",fg="#8A909C",font=("Segoe UI",7,"bold")).pack(anchor="w",padx=16); tk.Label(f,text=v,bg="white",fg=COLORS["ink"],font=("Segoe UI",19,"bold")).pack(anchor="w",padx=16); tk.Label(f,text=s,bg="white",fg=COLORS["muted"],font=("Segoe UI",8)).pack(anchor="w",padx=16,pady=(2,14))
        tk.Label(c,text="Priority actions",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",14,"bold")).pack(anchor="w",padx=34,pady=(18,7));
        actions=tk.Frame(c,bg=COLORS["bg"]); actions.pack(fill="x",padx=29)
        for i,(t,d,k) in enumerate([("Patients","Find and review patients","_patients"),("Clinical EHR","Encounters, prescriptions and documents","_ehr"),("Medication Records","Record treatment responses","_add_medication"),("Share / Export","Prepare authorized data exports","_share_export")]):
            f=tk.Frame(actions,bg="white",highlightbackground=COLORS["line"],highlightthickness=1); f.grid(row=0,column=i,padx=5,sticky="nsew"); actions.columnconfigure(i,weight=1); tk.Label(f,text=t,bg="white",fg=COLORS["ink"],font=("Segoe UI",10,"bold")).pack(anchor="w",padx=16,pady=(16,3)); tk.Label(f,text=d,bg="white",fg=COLORS["muted"],font=("Segoe UI",8),wraplength=180,justify="left").pack(anchor="w",padx=16,pady=(0,9)); tk.Button(f,text="Open →",command=lambda k=k:self._route(k),bd=0,bg="white",fg=COLORS["indigo"],activebackground="white",font=("Segoe UI",8,"bold"),cursor="hand2").pack(anchor="w",padx=16,pady=(0,15))

    def _open_patient(self,pid):
        pid=pid.strip().upper()
        if not pid: self._status("Enter a Patient ID.","warning"); return
        try:
            patient=get_patient_by_id(self.current_user,pid)
            if not patient: raise RecordGuardError("Patient not found.")
            self._show_clinical_patient(pid,patient)
        except Exception as exc: self._status(str(exc), "error")

    def _render_patients(self):
        c=self._page("Patients","Search patients and open the clinical workspace.")
        row=tk.Frame(c,bg=COLORS["bg"]); row.pack(fill="x",padx=34,pady=5); e=ttk.Entry(row,width=32); e.pack(side="left",ipady=3); ttk.Button(row,text="Search",style="Accent.TButton",command=lambda:self._search_patients(e.get())).pack(side="left",padx=8)
        if can_register_patients(self.current_user):
            ttk.Button(row,text="＋ Register patient",command=lambda:self._route("_register")).pack(side="left",padx=4)
        self._patient_tree=tk.Frame(c,bg=COLORS["bg"]); self._patient_tree.pack(fill="both",expand=True,padx=34,pady=10); self._search_patients("")
    def _search_patients(self,q):
        for w in self._patient_tree.winfo_children(): w.destroy()
        try: patients=list_all_patients(self.current_user)
        except Exception as exc: tk.Label(self._patient_tree,text=str(exc),bg=COLORS["bg"],fg=COLORS["red"]).pack(); return
        q=(q or "").strip().lower(); patients=[p for p in patients if not q or q in str(p.get("patient_id","")).lower() or q in str(p.get("name","")).lower() or q in str(p.get("phone_number","")).lower()]
        tree=ttk.Treeview(self._patient_tree,columns=("id","name","age","sex","blood"),show="headings"); self._tree_tags(tree);
        for k,h,w in [("id","Patient ID",140),("name","Name",220),("age","Age",80),("sex","Sex",100),("blood","Blood group",110)]: tree.heading(k,text=h); tree.column(k,width=w)
        tree.pack(fill="both",expand=True)
        for p in patients: tree.insert("","end",values=(p.get("patient_id"),p.get("name"),p.get("age"),p.get("sex"),p.get("blood_group") or "—"))
        self._tree_empty(self._patient_tree, tree, "No patients match this search. Register a patient or try another search.")
        tree.bind("<Double-1>",lambda e:self._open_patient(tree.item(tree.selection()[0],"values")[0]) if tree.selection() else None)

    # --------------------------- patient views ---------------------------
    def _render_personal_health(self):
        pid=self._patient_id(); p=get_patient_by_id(self.current_user,pid) or {}; c=self._page("My Health","Your complete health overview, organized into understandable sections.")
        f=self._card(c); tk.Label(f,text=p.get("name") or "Your profile",bg="white",fg=COLORS["ink"],font=("Segoe UI",17,"bold")).pack(anchor="w",padx=20,pady=(18,3)); tk.Label(f,text=f"Patient ID  •  {pid}",bg="white",fg=COLORS["teal"],font=("Segoe UI",9,"bold")).pack(anchor="w",padx=20,pady=(0,14))
        details=[("Date of birth",p.get("date_of_birth") or "Not provided"),("Age",p.get("age") or "Not provided"),("Sex",p.get("sex") or "Not provided"),("Blood group",p.get("blood_group") or "Not provided"),("Phone",p.get("phone_number") or "Not provided"),("Current address",p.get("current_address") or "Not provided")]
        grid=tk.Frame(f,bg="white"); grid.pack(fill="x",padx=20,pady=(0,15)); [grid.columnconfigure(i,weight=1) for i in range(2)]
        for i,(k,v) in enumerate(details): box=tk.Frame(grid,bg="white"); box.grid(row=i//2,column=i%2,padx=10,pady=8,sticky="ew"); tk.Label(box,text=k.upper(),bg="white",fg="#8A909C",font=("Segoe UI",7,"bold")).pack(anchor="w"); tk.Label(box,text=str(v),bg="white",fg=COLORS["ink"],font=("Segoe UI",10)).pack(anchor="w",pady=(2,0))
        note=self._card(c,COLORS["amber_soft"]); tk.Label(note,text="Explore your health",bg=COLORS["amber_soft"],fg="#7A5200",font=("Segoe UI",10,"bold")).pack(anchor="w",padx=18,pady=(12,3)); tk.Label(note,text="Open medicines, treatment memory or your clinical timeline without leaving My Health.",bg=COLORS["amber_soft"],fg="#8A6A2F",font=("Segoe UI",8)).pack(anchor="w",padx=18,pady=(0,8)); actions=tk.Frame(note,bg=COLORS["amber_soft"]); actions.pack(anchor="w",padx=18,pady=(0,13));
        for label,key in [("Medicines","_medicines"),("Treatment Memory","_treatment"),("Timeline","_timeline")]: ttk.Button(actions,text=label,command=lambda k=key:self._route(k)).pack(side="left",padx=(0,6))

    def _render_medicines(self):
        pid=self._patient_id(); c=self._page("Medicines","Complete underneath, simple on top: summary first, details and evidence when needed.")
        top=tk.Frame(c,bg=COLORS["bg"]); top.pack(fill="x",padx=34)
        if self._is_patient(): ttk.Button(top,text="＋ Add personal medicine",style="Accent.TButton",command=self._show_personal_medication).pack(side="left")
        else: ttk.Button(top,text="＋ Add clinical record",style="Accent.TButton",command=self._show_add_medication).pack(side="left")
        ttk.Button(top,text="▣ Scan prescription",style="Ghost.TButton",command=self._scan_prescription).pack(side="left",padx=8)
        if not pid: return
        try:
            rx=list_prescriptions(self.current_user,pid) if not self._is_patient() else []
            recs=self._records(pid)
            personal=list_personal_medications(self.current_user,pid) if self._is_patient() else []
        except Exception:
            rx=[]; recs=[]; personal=[]

        f=self._card(c); header=tk.Frame(f,bg="white"); header.pack(fill="x",padx=18,pady=(12,6))
        tk.Label(header,text="Medication summary",bg="white",fg=COLORS["ink"],font=("Segoe UI",13,"bold")).pack(side="left")
        sv=tk.StringVar(value="All")
        ttk.Combobox(header,textvariable=sv,values=["All","Active","Completed","Discontinued","Archived"],state="readonly",width=15).pack(side="right")
        tree=ttk.Treeview(f,columns=("uid","medicine","dose","freq","status","date"),show="headings",height=10)
        for k,h,w in [("uid","ID",120),("medicine","Medicine",220),("dose","Response / dose",180),("freq","Context",180),("status","Status",110),("date","Date",150)]: tree.heading(k,text=h); tree.column(k,width=w,anchor="w")
        tree.pack(fill="both",expand=True,padx=18,pady=6); self._tree_tags(tree)
        def filtered():
            choice=sv.get().upper();
            return [r for r in recs if choice=="ALL" or (r.get("status") or ("ARCHIVED" if r.get("is_archived") else "ACTIVE")).upper()==choice]
        def load():
            for i in tree.get_children(): tree.delete(i)
            rows=filtered()
            for i,r in enumerate(rows):
                status=(r.get("status") or ("ARCHIVED" if r.get("is_archived") else "ACTIVE")).title().replace("Admin_Deleted","Admin deleted")
                tree.insert("","end",iid=str(r.get("record_id")),values=(r.get("medication_uid") or f"MED-{int(r.get('record_id')):06d}",r.get("medicine_name"),r.get("response_type"),r.get("reason") or "—",status,r.get("record_date")),tags=("admin_deleted" if r.get("deleted_by_admin") else "archived" if r.get("is_archived") else "active",))
            self._tree_empty(f,tree,"No medication records match this status.")
        ttk.Button(header,text="Apply",style="Ghost.TButton",command=load).pack(side="right",padx=6)
        sv.trace_add("write",lambda *_:load())
        def detail(_=None):
            sel=tree.selection()
            if not sel: return
            r=next((x for x in recs if str(x.get("record_id"))==sel[0]),None)
            if not r: return
            w=tk.Toplevel(self); w.title(f"Medication {r.get('medication_uid') or r.get('record_id')}"); w.geometry("760x620")
            body=tk.Frame(w,bg=COLORS["bg"],padx=22,pady=18); body.pack(fill="both",expand=True)
            tk.Label(body,text=r.get("medicine_name") or "Medication",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",20,"bold")).pack(anchor="w")
            tk.Label(body,text=f"{r.get('medication_uid') or 'Medication ID'} · {r.get('status','ACTIVE').title()}",bg=COLORS["bg"],fg=COLORS["teal"],font=("Segoe UI",9,"bold")).pack(anchor="w",pady=(2,12))
            details=[("Response",r.get("response_type")),("Reaction",r.get("reaction") or "Not documented"),("Severity",r.get("severity") or "Not documented"),("Reason",r.get("reason") or "Not documented"),("Notes",r.get("notes") or "Not documented"),("Record date",r.get("record_date")),("Prescription",r.get("prescription_id") or "Not linked"),("Encounter",r.get("encounter_id") or "Not linked")]
            card=self._card(body); grid=tk.Frame(card,bg="white"); grid.pack(fill="x",padx=18,pady=14)
            for i,(lab,val) in enumerate(details):
                box=tk.Frame(grid,bg="white"); box.grid(row=i//2,column=i%2,sticky="ew",padx=10,pady=7); tk.Label(box,text=lab.upper(),bg="white",fg="#8A909C",font=("Segoe UI",7,"bold")).pack(anchor="w"); tk.Label(box,text=str(val),bg="white",fg=COLORS["ink"],font=("Segoe UI",9),wraplength=280,justify="left").pack(anchor="w")
            actions=tk.Frame(body,bg=COLORS["bg"]); actions.pack(fill="x",pady=7)
            if can_edit_records(self.current_user) and not r.get("is_archived") and not r.get("deleted_by_admin"):
                for label,status in [("Mark completed","COMPLETED"),("Mark discontinued","DISCONTINUED"),("Mark active","ACTIVE")]:
                    ttk.Button(actions,text=label,command=lambda st=status:self._set_med_status(r.get("record_id"),st,w)).pack(side="left",padx=3)
            hist=self._card(body,COLORS["gray_soft"]); tk.Label(hist,text="History / evidence",bg=COLORS["gray_soft"],fg=COLORS["ink"],font=("Segoe UI",11,"bold")).pack(anchor="w",padx=16,pady=(11,4))
            try: events=get_audit_log_for_record(self.current_user,int(r.get("record_id")))
            except Exception: events=[]
            for ev in events[:8]: tk.Label(hist,text=f"{ev.get('timestamp')} · {ev.get('action')} · {ev.get('result')}",bg=COLORS["gray_soft"],fg=COLORS["muted"],font=("Consolas",8)).pack(anchor="w",padx=16,pady=2)
            if not events: tk.Label(hist,text="No audit events available for this record.",bg=COLORS["gray_soft"],fg=COLORS["muted"],font=("Segoe UI",8)).pack(anchor="w",padx=16,pady=6)
        tree.bind("<Double-1>",detail)
        load()

        rxcard=self._card(c,COLORS["teal_soft"]); tk.Label(rxcard,text="Prescriptions",bg=COLORS["teal_soft"],fg=COLORS["teal"],font=("Segoe UI",11,"bold")).pack(anchor="w",padx=18,pady=(11,5))
        for r in rx[:8]: tk.Label(rxcard,text=f"{r.get('medicine_name')} · {' · '.join(x for x in [r.get('dosage'),r.get('frequency'),r.get('duration')] if x)}",bg=COLORS["teal_soft"],fg=COLORS["ink"],font=("Segoe UI",8)).pack(anchor="w",padx=18,pady=2)
        if not rx and not self._is_patient(): tk.Label(rxcard,text="No prescription entries yet.",bg=COLORS["teal_soft"],fg=COLORS["muted"],font=("Segoe UI",8)).pack(anchor="w",padx=18,pady=7)
        if self._is_patient() and personal:
            pc=self._card(c,COLORS["purple_soft"]); tk.Label(pc,text="Personal medicines",bg=COLORS["purple_soft"],fg=COLORS["purple"],font=("Segoe UI",11,"bold")).pack(anchor="w",padx=18,pady=(11,5))
            for r in personal[:8]: tk.Label(pc,text=f"{r.get('medicine_name')} · {' · '.join(x for x in [r.get('dosage'),r.get('frequency'),r.get('duration')] if x)}",bg=COLORS["purple_soft"],fg=COLORS["ink"],font=("Segoe UI",8)).pack(anchor="w",padx=18,pady=2)

    def _set_med_status(self,rid,status,parent):
        try: set_medication_status(self.current_user,rid,status); parent.destroy(); self._render_medicines(); self._status(f"Medication marked {status.title()}.","success")
        except Exception as exc: self._status(str(exc),"error",parent=parent)

    def _render_treatment(self):
        pid=self._patient_id() if self._is_patient() else None; c=self._page("Treatment Memory","What the documented treatment history shows — historical information only, not diagnosis or prescribing.")
        if not pid:
            row=tk.Frame(c,bg=COLORS["bg"]); row.pack(fill="x",padx=34); e=ttk.Entry(row,width=24); e.pack(side="left"); ttk.Button(row,text="Open",style="Accent.TButton",command=lambda:self._render_clinical_treatment(e.get())).pack(side="left",padx=8); return
        self._render_treatment_cards(c,pid)
    def _render_clinical_treatment(self,pid):
        c=self._page("Treatment Memory","Evidence-first historical patterning for the selected patient."); self._render_treatment_cards(c,pid.strip().upper())
    def _render_treatment_cards(self,c,pid):
        try: recs=self._records(pid)
        except Exception as exc: tk.Label(c,text=str(exc),bg=COLORS["bg"],fg=COLORS["red"]).pack(); return
        for r in recs:
            rt=r.get("response_type") or "Unknown"; color=COLORS["red"] if rt in ("Allergy","Adverse reaction") else COLORS["green"] if rt=="Effective" else COLORS["amber"] if rt=="Ineffective" else COLORS["blue"]
            soft=COLORS["red_soft"] if color==COLORS["red"] else COLORS["green_soft"] if color==COLORS["green"] else COLORS["amber_soft"] if color==COLORS["amber"] else COLORS["blue_soft"]
            f=self._card(c,soft); head=tk.Frame(f,bg=soft); head.pack(fill="x",padx=16,pady=(12,2)); tk.Label(head,text=r.get("medicine_name"),bg=soft,fg=COLORS["ink"],font=("Segoe UI",10,"bold")).pack(side="left"); self._pill(head,rt,color,"white").pack(side="right"); tk.Label(f,text=f"{r.get('record_date','')}  ·  {r.get('reason') or 'Treatment response documented'}",bg=soft,fg=COLORS["muted"],font=("Segoe UI",8)).pack(anchor="w",padx=16,pady=(3,5)); tk.Label(f,text="Medication → Context → Outcome → Date → Evidence → Verification",bg=soft,fg=COLORS["muted"],font=("Segoe UI",8)).pack(anchor="w",padx=16,pady=(0,12))
        note=self._card(c,COLORS["purple_soft"]); tk.Label(note,text="AI assists. Evidence supports. Clinician decides.",bg=COLORS["purple_soft"],fg="#4B4295",font=("Segoe UI",9,"bold")).pack(anchor="w",padx=16,pady=(12,2)); tk.Label(note,text="RecordGuard surfaces documented history and does not diagnose, prescribe or independently determine safety.",bg=COLORS["purple_soft"],fg="#6B668A",font=("Segoe UI",8)).pack(anchor="w",padx=16,pady=(0,12))

    def _render_timeline(self):
        pid=self._patient_id() if self._is_patient() else None
        if not pid:
            c=self._page("Timeline","Select a patient to view the clinical story."); row=tk.Frame(c,bg=COLORS["bg"]); row.pack(fill="x",padx=34); e=ttk.Entry(row,width=24); e.pack(side="left"); ttk.Button(row,text="Open",style="Accent.TButton",command=lambda:self._clinical_timeline(e.get())).pack(side="left",padx=8); return
        self._clinical_timeline(pid)
    def _clinical_timeline(self,pid):
        c=self._page("Clinical Timeline","Documented events, color-coded by information type."); pid=pid.strip().upper()
        events=[]
        for r in self._records(pid): events.append((r.get("record_date",""),"💊","Medication",r.get("medicine_name"),r.get("response_type")))
        try:
            for e in list_encounters(self.current_user,pid): events.append((e.get("visit_date",""),"🩺","Clinical",e.get("visit_type") or "Clinical visit",e.get("chief_complaint") or ""))
            for rx in list_prescriptions(self.current_user,pid): events.append((rx.get("created_at",""),"💊","Prescription",rx.get("medicine_name"),rx.get("dosage") or ""))
            for a in list_attachments(self.current_user,pid): events.append((a.get("created_at",""),"📄","Document",a.get("original_name"),a.get("mime_type") or ""))
        except Exception: pass
        events.sort(reverse=True)
        for d,ic,typ,title,detail in events:
            color=COLORS["purple"] if typ in ("Medication","Prescription") else COLORS["indigo"] if typ=="Clinical" else COLORS["blue"] if typ=="Document" else COLORS["teal"]
            f=tk.Frame(c,bg="white",highlightbackground=COLORS["line"],highlightthickness=1); f.pack(fill="x",padx=34,pady=5); tk.Label(f,text=ic,bg="white",fg=color,font=("Segoe UI",13)).pack(side="left",padx=16,pady=12); q=tk.Frame(f,bg="white"); q.pack(side="left",fill="x",expand=True,pady=10); tk.Label(q,text=f"{title}  ·  {typ}",bg="white",fg=COLORS["ink"],font=("Segoe UI",9,"bold")).pack(anchor="w"); tk.Label(q,text=f"{detail}  ·  {d}",bg="white",fg=COLORS["muted"],font=("Segoe UI",8)).pack(anchor="w",pady=(2,0))
        if not events: tk.Label(c,text="No timeline events are available.",bg=COLORS["bg"],fg=COLORS["muted"]).pack(padx=34,pady=20,anchor="w")

    def _render_passport(self):
        if not self._is_patient(): self._render_clinical_treatment(None); return
        pid=self._patient_id(); p=get_patient_by_id(self.current_user,pid) or {}; recs=self._records(pid); c=self._page("Safety Passport","A compact, share-ready view of important documented safety information.")
        f=self._card(c,COLORS["teal_soft"]); tk.Label(f,text="🛡  RECORDGUARD SAFETY PASSPORT",bg=COLORS["teal_soft"],fg="#08766F",font=("Segoe UI",15,"bold")).pack(anchor="w",padx=20,pady=(17,3)); tk.Label(f,text=f"{p.get('name','')}  ·  {pid}",bg=COLORS["teal_soft"],fg="#54716D",font=("Segoe UI",9)).pack(anchor="w",padx=20,pady=(0,12))
        safety=[x for x in recs if x.get("response_type") in ("Allergy","Adverse reaction")]
        for r in safety:
            a=tk.Frame(f,bg=COLORS["red_soft"]); a.pack(fill="x",padx=20,pady=4); tk.Label(a,text=f"🔴 {r.get('medicine_name')} — {r.get('response_type')} · {r.get('severity') or 'severity not documented'}",bg=COLORS["red_soft"],fg=COLORS["red"],font=("Segoe UI",9,"bold")).pack(anchor="w",padx=12,pady=8)
        if not safety: tk.Label(f,text="No documented allergy/adverse-reaction records.",bg=COLORS["teal_soft"],fg="#54716D",font=("Segoe UI",9)).pack(anchor="w",padx=20,pady=8)
        try:
            personal=list_personal_medications(self.current_user,pid); names=[x.get("medicine_name") for x in personal if x.get("medicine_name")]
            tk.Label(f,text="Current personal medicines",bg=COLORS["teal_soft"],fg="#286B60",font=("Segoe UI",10,"bold")).pack(anchor="w",padx=20,pady=(8,3)); tk.Label(f,text=", ".join(names[:12]) if names else "No personal medicines documented.",bg=COLORS["teal_soft"],fg="#54716D",font=("Segoe UI",9),wraplength=800,justify="left").pack(anchor="w",padx=20,pady=(0,8))
        except Exception:
            pass

        ttk.Button(f,text="Share / Export Passport",style="Accent.TButton",command=lambda:self._route("_share_export")).pack(anchor="w",padx=20,pady=15)

    def _render_privacy(self):
        if not self._is_patient():
            self._render_privacy_hub(); return
        pid=self._patient_id(); c=self._page("Privacy & Sharing","You control what is shared, for how long, and can see access activity.")
        f=self._card(c,COLORS["teal_soft"]); tk.Label(f,text="🛡 You're in control",bg=COLORS["teal_soft"],fg=COLORS["teal"],font=("Segoe UI",14,"bold")).pack(anchor="w",padx=18,pady=(14,3)); tk.Label(f,text="Sharing never expands the underlying permission scope.",bg=COLORS["teal_soft"],fg="#54716D",font=("Segoe UI",8)).pack(anchor="w",padx=18,pady=(0,12))
        ttk.Button(f,text="Share / Export health data",style="Accent.TButton",command=lambda:self._route("_share_export")).pack(side="left",padx=18,pady=(0,14)); ttk.Button(f,text="View access history",style="Ghost.TButton",command=lambda:self._route("_access")).pack(side="left",padx=6,pady=(0,14))
        corr=self._card(c,COLORS["amber_soft"]); tk.Label(corr,text="Correction requests",bg=COLORS["amber_soft"],fg="#7A5200",font=("Segoe UI",10,"bold")).pack(anchor="w",padx=18,pady=(12,3)); tk.Label(corr,text="Verified records are not silently overwritten. Submit a request for authorized review.",bg=COLORS["amber_soft"],fg="#8A6A2F",font=("Segoe UI",8)).pack(anchor="w",padx=18,pady=(0,8)); ttk.Button(corr,text="Request a correction",command=self._correction_dialog).pack(anchor="w",padx=18,pady=(0,13))

    def _render_access(self):
        if not self._is_patient(): self._show_access_for_patient_prompt(); return
        c=self._page("Access History","See who accessed your records and what they accessed.")
        try: logs=get_patient_access_history(self.current_user,self._patient_id())
        except Exception as exc: logs=[]; tk.Label(c,text=str(exc),bg=COLORS["bg"],fg=COLORS["red"]).pack()
        tree=ttk.Treeview(c,columns=("user","role","action","time"),show="headings"); tree.pack(fill="both",expand=True,padx=34,pady=8)
        for k,h,w in [("user","User",150),("role","Role",100),("action","Action",380),("time","Timestamp",180)]: tree.heading(k,text=h); tree.column(k,width=w)
        for x in logs: tree.insert("","end",values=(x.get("username"),x.get("role"),x.get("action"),x.get("timestamp")))
        if not logs: tk.Label(c,text="No access events yet.",bg=COLORS["bg"],fg=COLORS["muted"]).pack(anchor="w",padx=34,pady=10)

    def _show_access_for_patient_prompt(self): self._status("Access history is available to the linked patient account and authorized clinical workflows.", "info")

    def _render_share_export(self):
        pid=self._patient_id() if self._is_patient() else None; c=self._page("Share / Export","Select exactly what you need. Exporting creates a file; sharing creates controlled access.")
        row=tk.Frame(c,bg=COLORS["bg"]); row.pack(fill="x",padx=34,pady=5); tk.Label(row,text="Patient ID",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",9,"bold")).pack(side="left"); e=ttk.Entry(row,width=22); e.pack(side="left",padx=8); e.insert(0,pid or "");
        if self._is_patient(): e.config(state="disabled")
        checks={}; box=self._card(c); tk.Label(box,text="1. Choose information",bg="white",fg=COLORS["ink"],font=("Segoe UI",12,"bold")).pack(anchor="w",padx=18,pady=(15,8))
        for k,label in [("medicines","Medicines"),("treatment","Treatment Memory"),("encounters","Clinical history / encounters"),("prescriptions","Prescriptions"),("documents","Original documents / metadata"),("passport","Safety Passport")]:
            v=tk.BooleanVar(value=k in ("medicines","treatment","passport")); checks[k]=v; tk.Checkbutton(box,text=label,variable=v,bg="white",activebackground="white",font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=2)
        tk.Label(box,text="2. Date range",bg="white",fg=COLORS["ink"],font=("Segoe UI",9,"bold")).pack(anchor="w",padx=18,pady=(12,4)); datev=tk.StringVar(value="All time"); datecb=ttk.Combobox(box,textvariable=datev,values=["All time","Last 7 days","Last 30 days","Last 90 days","Custom"],state="readonly",width=18); datecb.pack(anchor="w",padx=18)
        custom=tk.Frame(box,bg="white"); custom.pack(anchor="w",padx=18,pady=5); frm=ttk.Entry(custom,width=12); to=ttk.Entry(custom,width=12); tk.Label(custom,text="From YYYY-MM-DD",bg="white").pack(side="left"); frm.pack(side="left",padx=5); tk.Label(custom,text="To",bg="white").pack(side="left"); to.pack(side="left",padx=5)
        tk.Label(box,text="3. Format",bg="white",fg=COLORS["ink"],font=("Segoe UI",9,"bold")).pack(anchor="w",padx=18,pady=(12,4)); fmt=ttk.Combobox(box,values=["PDF Health Summary","JSON","CSV","FHIR-inspired JSON","Original documents (ZIP)"],state="readonly",width=28); fmt.set("PDF Health Summary"); fmt.pack(anchor="w",padx=18)
        tk.Label(box,text="4. Controlled share recipient (leave blank for export only)",bg="white",fg=COLORS["ink"],font=("Segoe UI",9,"bold")).pack(anchor="w",padx=18,pady=(12,4)); recipient=ttk.Entry(box,width=32); recipient.pack(anchor="w",padx=18)
        tk.Label(box,text="Access duration",bg="white",fg=COLORS["ink"],font=("Segoe UI",9,"bold")).pack(anchor="w",padx=18,pady=(12,4)); dur=ttk.Combobox(box,values=["1 hour","24 hours","7 days","30 days"],state="readonly",width=18); dur.set("24 hours"); dur.pack(anchor="w",padx=18)
        actions=tk.Frame(box,bg="white"); actions.pack(fill="x",padx=18,pady=16); ttk.Button(actions,text="Preview selection",style="Accent.TButton",command=lambda:self._preview_export(e.get(),checks,datev.get(),frm.get(),to.get(),fmt.get())).pack(side="left"); ttk.Button(actions,text="Create controlled share",style="Ghost.TButton",command=lambda:self._do_share(e.get(),checks,recipient.get(),dur.get())).pack(side="left",padx=8)
        if self._is_patient() or self._role() in {"owner","admin","doctor","staff"}:
            sf=self._card(c,COLORS["teal_soft"]); tk.Label(sf,text="Active shares",bg=COLORS["teal_soft"],fg=COLORS["teal"],font=("Segoe UI",11,"bold")).pack(anchor="w",padx=18,pady=(12,5));
            try:
                shares=list_record_shares(self.current_user,pid) if pid else []
                for sh in shares[:20]:
                    expired=bool(sh.get("expires_at") and datetime.fromisoformat(sh["expires_at"])<=datetime.now()); status="Revoked" if sh.get("revoked") else ("Expired" if expired else "Active")
                    row=tk.Frame(sf,bg=COLORS["teal_soft"]); row.pack(fill="x",padx=18,pady=3); tk.Label(row,text=f"#{sh.get('share_id')} · {sh.get('shared_with')} · {status} · expires {sh.get('expires_at') or 'never'}",bg=COLORS["teal_soft"],fg=COLORS["ink"]).pack(side="left")
                    if status=="Active":
                        ttk.Button(row,text="Revoke",command=lambda sid=sh.get('share_id'): self._revoke_share(sid)).pack(side="right",padx=3)
                        ttk.Button(row,text="Copy token",command=lambda tok=sh.get('share_token'): self._copy_token(tok)).pack(side="right",padx=3)
                    tk.Label(sf,text=f"Token: {sh.get('share_token')}",bg=COLORS["teal_soft"],fg=COLORS["muted"],font=("Consolas",7),wraplength=850).pack(anchor="w",padx=18)
            except Exception as exc: tk.Label(sf,text=str(exc),bg=COLORS["teal_soft"],fg=COLORS["red"]).pack(anchor="w",padx=18)

    def _date_bounds(self,choice,start,end):
        now=datetime.now(); choice=str(choice or "All time")
        if choice=="Last 7 days": return now-timedelta(days=7),now
        if choice=="Last 30 days": return now-timedelta(days=30),now
        if choice=="Last 90 days": return now-timedelta(days=90),now
        if choice=="Custom":
            try: return datetime.fromisoformat(start.strip()), datetime.fromisoformat(end.strip())+timedelta(days=1)-timedelta(seconds=1)
            except Exception: raise RecordGuardError("Use valid custom dates in YYYY-MM-DD format.")
        return None,None

    def _collect_data(self,pid,checks,start_choice="All time",start="",end=""):
        pid=pid.strip().upper(); patient=get_patient_by_id(self.current_user,pid); lo,hi=self._date_bounds(start_choice,start,end); data={"patient":patient,"exported_at":datetime.now().isoformat(timespec="seconds"),"selection":{k:v.get() for k,v in checks.items()},"date_range":{"from":lo.isoformat() if lo else None,"to":hi.isoformat() if hi else None}}
        def filt(items,*keys):
            if not lo:return items
            out=[]
            for x in items:
                val=next((x.get(k) for k in keys if x.get(k)),None)
                try:
                    dt=datetime.fromisoformat(str(val).replace("Z",""))
                    if lo<=dt<=hi: out.append(x)
                except Exception: out.append(x)
            return out
        if checks["medicines"].get() or checks["treatment"].get(): data["medication_records"]=filt(self._records(pid),"record_date")
        if checks["encounters"].get(): data["encounters"]=filt(list_encounters(self.current_user,pid),"visit_date","created_at")
        if checks["prescriptions"].get(): data["prescriptions"]=filt(list_prescriptions(self.current_user,pid),"created_at")
        if checks["documents"].get(): data["attachments"]=filt(list_attachments(self.current_user,pid),"created_at")
        if checks["passport"].get():
            data["safety_records"]=[r for r in filt(self._records(pid),"record_date") if r.get("response_type") in {"Allergy","Adverse reaction"}]
            try: data["personal_medications"]=filt(list_personal_medications(self.current_user,pid),"created_at")
            except Exception: data["personal_medications"]=[]
        return data

    def _preview_export(self,pid,checks,choice,start,end,fmt):
        try:
            if not pid.strip(): raise RecordGuardError("Patient ID is required.")
            data=self._collect_data(pid,checks,choice,start,end); w=tk.Toplevel(self); w.title("Review before export"); w.geometry("720x560"); f=tk.Frame(w,bg=COLORS["bg"],padx=20,pady=18); f.pack(fill="both",expand=True); tk.Label(f,text="Review exactly what will be exported",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",20,"bold")).pack(anchor="w");
            summary=[]
            for k,label in [("medication_records","Medicines / treatment"),("encounters","Encounters"),("prescriptions","Prescriptions"),("attachments","Documents")]:
                if k in data: summary.append(f"{label}: {len(data[k])}")
            summary.append(f"Format: {fmt}"); summary.append(f"Date range: {choice}")
            tk.Label(f,text="\n".join(summary),bg="white",fg=COLORS["ink"],font=("Segoe UI",10),justify="left",anchor="w",padx=15,pady=15).pack(fill="x",pady=15); tk.Label(f,text="Only information allowed by your existing role and patient scope is included.",bg=COLORS["teal_soft"],fg=COLORS["teal"],padx=10,pady=9).pack(fill="x"); ttk.Button(f,text="Export this selection",style="Accent.TButton",command=lambda:(w.destroy(),self._do_export_data(data,fmt))).pack(anchor="e",pady=15); ttk.Button(f,text="Cancel",command=w.destroy).pack(anchor="e")
        except Exception as exc: self._status(str(exc), "error")

    def _do_export_data(self,data,fmt):
        try:
            ext=".pdf" if fmt.startswith("PDF") else ".csv" if fmt=="CSV" else ".zip" if "ZIP" in fmt else ".json"; path=filedialog.asksaveasfilename(parent=self,title="Export RecordGuard data",defaultextension=ext,filetypes=[("All files","*.*")]);
            if not path:return
            if fmt.startswith("PDF"): self._export_pdf(data,path)
            elif fmt=="CSV": self._export_csv(data,path)
            elif fmt=="Original documents (ZIP)": self._export_documents(data,path)
            else:
                payload=patient_to_bundle(data["patient"],data.get("medication_records",[]),data.get("encounters",[]),data.get("prescriptions",[]),data.get("attachments",[])) if fmt.startswith("FHIR") else data
                if isinstance(payload, dict) and "attachments" in payload:
                    payload = dict(payload)
                    payload["attachments"] = [{k:v for k,v in item.items() if k != "stored_path"} for item in payload.get("attachments",[])]
                with open(path,"w",encoding="utf-8") as f: json.dump(payload,f,indent=2,ensure_ascii=False)
            self._status(f"Export created successfully: {path}", "success")
        except Exception as exc: self._status(str(exc), "error")

    def _do_export(self,pid,checks,fmt): self._preview_export(pid,checks,"All time","","",fmt)

    def _export_pdf(self,data,path):
        if not REPORTLAB: raise RecordGuardError("PDF export requires ReportLab. Install the packages in requirements.txt.")
        styles=getSampleStyleSheet(); doc=SimpleDocTemplate(path,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=40); story=[]
        patient=data.get("patient") or {}; story.append(Paragraph("RecordGuard Health Summary",styles["Title"])); story.append(Spacer(1,10)); story.append(Paragraph(f"Patient: {patient.get('name','')} · ID: {patient.get('patient_id','')}",styles["Normal"])); story.append(Paragraph(f"Generated: {data.get('exported_at','')}",styles["Normal"])); story.append(Spacer(1,12))
        if data.get("date_range",{}).get("from"): story.append(Paragraph(f"Date range: {data['date_range']['from']} to {data['date_range']['to']}",styles["Normal"])); story.append(Spacer(1,8))
        sections=[("Medication / treatment records",data.get("medication_records",[]),["medicine_name","response_type","reaction","reason","record_date"]),("Encounters",data.get("encounters",[]),["visit_date","visit_type","chief_complaint","diagnoses"]),("Prescriptions",data.get("prescriptions",[]),["created_at","medicine_name","dosage","frequency","duration","prescribed_by"]),("Safety Passport",data.get("safety_records",[]),["medicine_name","response_type","severity","reaction","record_date"]),("Personal medicines",data.get("personal_medications",[]),["created_at","medicine_name","dosage","frequency","duration","route"]),("Documents",data.get("attachments",[]),["created_at","original_name","mime_type","uploaded_by"])]
        for title,items,keys in sections:
            if not items: continue
            story.append(Paragraph(title,styles["Heading2"])); rows=[[k.replace("_"," ").title() for k in keys]]
            for item in items[:100]: rows.append([str(item.get(k) or "")[:180] for k in keys])
            t=Table(rows,repeatRows=1); t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.4,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("VALIGN",(0,0),(-1,-1),"TOP")])); story.append(t); story.append(Spacer(1,10))
        story.append(Paragraph("RecordGuard organizes documented health information. This summary is not a diagnosis or prescribing recommendation.",styles["Italic"])); doc.build(story)

    def _export_documents(self,data,path):
        attachments=data.get("attachments",[])
        if not attachments: raise RecordGuardError("No original documents were selected or available for export.")
        base=os.path.dirname(os.path.abspath(__file__)); added=0
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
            for item in attachments:
                stored=item.get("stored_path")
                if not stored: continue
                full=os.path.abspath(os.path.join(base,stored))
                try: safe=os.path.commonpath([base,full])==base
                except ValueError: safe=False
                if not safe or not os.path.isfile(full): continue
                name=os.path.basename(item.get("original_name") or full); z.write(full,os.path.join("documents",name)); added+=1
            if not added: raise RecordGuardError("The selected original documents could not be found on this device.")

    def _export_csv(self,data,path):
        rows=[]
        for r in data.get("medication_records",[]): rows.append({"type":"medication","id":r.get("record_id"),"patient_id":r.get("patient_id"),"name":r.get("medicine_name"),"response":r.get("response_type"),"details":r.get("reaction") or r.get("reason"),"date":r.get("record_date")})
        for r in data.get("encounters",[]): rows.append({"type":"encounter","id":r.get("encounter_id"),"patient_id":r.get("patient_id"),"name":r.get("visit_type"),"response":r.get("chief_complaint"),"details":r.get("visit_notes"),"date":r.get("visit_date")})
        for r in data.get("prescriptions",[]): rows.append({"type":"prescription","id":r.get("prescription_id"),"patient_id":r.get("patient_id"),"name":r.get("medicine_name"),"response":r.get("dosage"),"details":r.get("frequency") or r.get("duration"),"date":r.get("created_at")})
        for r in data.get("attachments",[]): rows.append({"type":"document","id":r.get("attachment_id"),"patient_id":r.get("patient_id"),"name":r.get("original_name"),"response":r.get("mime_type"),"details":r.get("mime_type"),"date":r.get("created_at")})
        with open(path,"w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=["type","id","patient_id","name","response","details","date"]); w.writeheader(); w.writerows(rows)

    def _copy_token(self,token):
        try:
            self.clipboard_clear(); self.clipboard_append(str(token or "")); self._status("Secure share token copied to the clipboard.", "success")
        except Exception as exc: self._status(str(exc), "error")

    def _revoke_share(self,sid):
        try: revoke_record_share(self.current_user,int(sid)); self._status("Share access revoked.", "success"); self._render_share_export()
        except Exception as exc: self._status(str(exc), "error")

    def _do_share(self,pid,checks,recipient,duration):
        try:
            if not recipient.strip(): raise RecordGuardError("Recipient is required for a controlled share.")
            if self._role()=="patient" and pid.strip().upper()!=self._patient_id().strip().upper(): raise RecordGuardError("Patients can only share their own records.")
            pid=pid.strip().upper(); items=[]
            if checks["medicines"].get() or checks["treatment"].get(): items += [("medication",x.get("record_id")) for x in self._records(pid)]
            if checks["encounters"].get(): items += [("encounter",x.get("encounter_id")) for x in list_encounters(self.current_user,pid)]
            if checks["prescriptions"].get(): items += [("prescription",x.get("prescription_id")) for x in list_prescriptions(self.current_user,pid)]
            if checks["documents"].get() or checks["passport"].get(): items += [("document",x.get("attachment_id")) for x in list_attachments(self.current_user,pid)]
            if not items: raise RecordGuardError("Select at least one category with available records.")
            hours={"1 hour":1,"24 hours":24,"7 days":168,"30 days":720}[duration]; expiry=(datetime.now()+timedelta(hours=hours)).isoformat(timespec="seconds")
            valid_items=[(typ,int(rid)) for typ,rid in items if rid]
            shares=create_record_shares_batch(self.current_user,pid,valid_items,recipient,expiry)
            self._status(f"{len(shares)} secure share(s) created for {recipient}. Tokens are available under Active shares.", "success"); self._render_share_export()
        except Exception as exc: self._status(str(exc), "error")

    # --------------------------- clinical patient ---------------------------
    def _show_clinical_patient(self,pid,patient):
        c=self._page(f"Patient — {patient.get('name','')}",f"{pid}  ·  Relevant treatment history first, then timeline and evidence.")
        recs=self._records(pid); alerts=[r for r in recs if r.get("response_type") in ("Allergy","Adverse reaction")]
        head=self._card(c); tk.Label(head,text=f"{patient.get('name','')}   {pid}",bg="white",fg=COLORS["ink"],font=("Segoe UI",17,"bold")).pack(anchor="w",padx=18,pady=(15,2)); tk.Label(head,text=f"Age {patient.get('age','—')}  ·  {patient.get('sex','—')}  ·  Blood group {patient.get('blood_group') or '—'}",bg="white",fg=COLORS["muted"],font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=(0,12))
        if alerts:
            f=self._card(c,COLORS["red_soft"]); tk.Label(f,text="⚠ Relevant treatment history",bg=COLORS["red_soft"],fg=COLORS["red"],font=("Segoe UI",11,"bold")).pack(anchor="w",padx=18,pady=(12,5));
            for r in alerts[:5]: tk.Label(f,text=f"{r.get('medicine_name')} — {r.get('response_type')} · {r.get('record_date','')} · clinician/record evidence",bg=COLORS["red_soft"],fg="#7A3030",font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=3)
        actions=tk.Frame(c,bg=COLORS["bg"]); actions.pack(fill="x",padx=34,pady=5); ttk.Button(actions,text="Clinical EHR",style="Accent.TButton",command=lambda:self._show_ehr_for(pid)).pack(side="left"); ttk.Button(actions,text="Treatment Memory",style="Ghost.TButton",command=lambda:self._render_clinical_treatment(pid)).pack(side="left",padx=7); ttk.Button(actions,text="Timeline",style="Ghost.TButton",command=lambda:self._clinical_timeline(pid)).pack(side="left")
        f=self._card(c); tk.Label(f,text="Current medicines / prescriptions",bg="white",fg=COLORS["ink"],font=("Segoe UI",12,"bold")).pack(anchor="w",padx=18,pady=(13,7));
        try: rx=list_prescriptions(self.current_user,pid)
        except Exception: rx=[]
        for x in rx[:8]: tk.Label(f,text=f"💊 {x.get('medicine_name')}  ·  {x.get('dosage') or ''}  ·  {x.get('frequency') or ''}",bg="white",fg=COLORS["ink"],font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=3)

    def _show_ehr_for(self,pid): self._show_ehr(pid)

    # --------------------------- forms / EHR ---------------------------
    def _open_creation_hub(self):
        role=self._role()
        if role not in {"owner","admin","doctor","staff"}:
            self._deny(); return
        w=tk.Toplevel(self); w.title("RecordGuard — Create person / account"); w.geometry("560x430"); w.transient(self); w.grab_set()
        f=tk.Frame(w,bg="white",padx=28,pady=24); f.pack(fill="both",expand=True)
        tk.Label(f,text="Create person / account",bg="white",fg=COLORS["ink"],font=("Segoe UI",20,"bold")).pack(anchor="w")
        descriptions={
            "owner":"Owner can provision Admin, Doctor, Staff or Patient accounts.",
            "admin":"Admin can provision Doctor, Staff or Patient accounts.",
            "doctor":"Doctor can register patient profiles only.",
            "staff":"Staff can register patient profiles only.",
        }
        tk.Label(f,text=descriptions[role],bg="white",fg=COLORS["muted"],font=("Segoe UI",9),wraplength=470,justify="left").pack(anchor="w",pady=(5,18))
        if role == "owner":
            options=[
                ("Create staff / doctor / admin account","_users","Provision an authorised login account according to the hierarchy"),
                ("Register patient","_register","Create a patient profile; this does not create a login account"),
            ]
        elif role == "admin":
            options=[
                ("Create staff / doctor account","_users","Provision an authorised login account; Admin cannot create another Admin or Owner"),
                ("Register patient","_register","Create a patient profile; this does not create a login account"),
            ]
        else:
            options=[
                ("Register patient","_register","Create a patient profile; this does not create a login account"),
            ]
        for title,key,desc in options:
            card=tk.Frame(f,bg=COLORS["indigo_soft"],highlightbackground=COLORS["line"],highlightthickness=1); card.pack(fill="x",pady=6)
            tk.Label(card,text=title,bg=COLORS["indigo_soft"],fg=COLORS["indigo_dark"],font=("Segoe UI",11,"bold")).pack(anchor="w",padx=14,pady=(10,2))
            tk.Label(card,text=desc,bg=COLORS["indigo_soft"],fg=COLORS["muted"],font=("Segoe UI",8)).pack(anchor="w",padx=14)
            ttk.Button(card,text="Open",style="Accent.TButton",command=lambda k=key:(w.destroy(),self._route(k))).pack(anchor="e",padx=14,pady=9)
        ttk.Button(f,text="Cancel",command=w.destroy).pack(anchor="w",pady=(10,0))

    def _show_register(self):
        if not can_register_patients(self.current_user): self._deny(); return
        c=self._page("Register Patient","Create a patient profile only. A unique Patient ID is generated automatically; no login account is created here.")
        form=self._card(c); fields={}; validators={
            "name": validate_name, "age": validate_age, "sex": validate_sex
        }
        labels=[("Name","name"),("Age","age"),("Sex","sex"),("Date of birth","dob"),("Permanent address","perm"),("Current address","current"),("Phone","phone"),("Blood group","blood")]
        for i,(lab,key) in enumerate(labels):
            v=validators.get(key)
            if key in {"sex", "blood"}:
                tk.Label(form,text=lab,bg="white",fg="#52586A",font=("Segoe UI",8,"bold")).grid(row=i*2,column=0,sticky="nw",padx=16,pady=(7,2))
                values=("M","F","Other") if key == "sex" else ("A+","A-","B+","B-","AB+","AB-","O+","O-")
                entry=ttk.Combobox(form,values=values,state="readonly",width=42)
                entry.grid(row=i*2,column=1,sticky="ew",padx=16,pady=(7,0))
                err=tk.Label(form,text="",bg="white",fg=COLORS["red"],font=("Segoe UI",8),anchor="w")
                err.grid(row=i*2+1,column=1,sticky="w",padx=16,pady=(0,4))
                self._field_validator(entry,v,err)
                fields[key]=entry
            else:
                fields[key], _err = self._add_field(form, i*2, lab, key, v)
        form.columnconfigure(1,weight=1)
        def save():
            errors=[]
            from validation import validate_patient_registration
            errors=validate_patient_registration(fields["name"].get(),fields["age"].get(),fields["sex"].get(),fields["dob"].get(),fields["perm"].get(),fields["current"].get(),fields["phone"].get(),fields["blood"].get())
            if errors:
                self._status(" ".join(errors), "error"); return
            try:
                p=register_patient(self.current_user,fields["name"].get(),fields["age"].get(),fields["sex"].get(),fields["dob"].get(),fields["perm"].get(),fields["current"].get(),fields["phone"].get(),fields["blood"].get())
                self._route("_patients")
                self._status(f"Patient created successfully: {p['patient_id']}", "success")
            except Exception as exc: self._status(str(exc),"error")
        ttk.Button(form,text="Create patient",style="Accent.TButton",command=save).grid(row=len(labels)*2,column=1,sticky="w",padx=16,pady=14)

    def _show_personal_medication(self):
        if not self._is_patient(): self._deny(); return
        pid=self._patient_id(); w=tk.Toplevel(self); w.title("Add personal medicine"); w.geometry("520x420"); w.transient(self); w.grab_set(); f=tk.Frame(w,bg="white",padx=20,pady=20); f.pack(fill="both",expand=True); es={}
        for i,(lab,key) in enumerate([("Medicine name","med"),("Strength / dosage","dose"),("Frequency","freq"),("Duration","dur"),("Route","route"),("Instructions","inst")]): tk.Label(f,text=lab,bg="white",fg=COLORS["ink"]).grid(row=i,column=0,sticky="w",pady=6); e=ttk.Entry(f,width=40); e.grid(row=i,column=1,pady=6); es[key]=e
        def save():
            try: add_personal_medication(self.current_user,pid,es["med"].get(),es["dose"].get(),es["freq"].get(),es["dur"].get(),es["route"].get(),es["inst"].get(),"Manual entry","User verified"); w.destroy(); self._render_medicines()
            except Exception as exc: self._status(str(exc), "error", parent=w)
        ttk.Button(f,text="Save personal medicine",style="Accent.TButton",command=save).grid(row=6,column=1,sticky="w",pady=12)

    def _show_add_medication(self):
        if not can_add_records(self.current_user): self._deny(); return
        c=self._page("Medication Record","Record a documented treatment response. Patient accounts cannot create clinical records.")
        form=self._card(c); entries={}
        fields=[("Patient ID","pid",validate_patient_id_format),("Medicine name","med",validate_medicine_name),("Response","resp",validate_response_type),("Reaction","reaction",None),("Severity","severity",None),("Reason","reason",None)]
        for i,(lab,key,validator) in enumerate(fields):
            tk.Label(form,text=lab,bg="white",fg="#52586A",font=("Segoe UI",8,"bold")).grid(row=i*2,column=0,sticky="nw",padx=16,pady=(7,2))
            if key=="resp": w=ttk.Combobox(form,values=RESPONSE_TYPES,state="readonly",width=42); w.set("Unknown")
            elif key=="severity": w=ttk.Combobox(form,values=SEVERITY_LEVELS,state="readonly",width=42); w.set("")
            else: w=ttk.Entry(form,width=44)
            w.grid(row=i*2,column=1,sticky="ew",padx=16,pady=(7,0)); entries[key]=w
            err=tk.Label(form,text="",bg="white",fg=COLORS["red"],font=("Segoe UI",8)); err.grid(row=i*2+1,column=1,sticky="w",padx=16,pady=(0,4))
            if validator: self._field_validator(w,validator,err)
        if self._is_patient(): entries["pid"].insert(0,self._patient_id() or ""); entries["pid"].config(state="disabled")
        tk.Label(form,text="Notes",bg="white",fg="#52586A",font=("Segoe UI",8,"bold")).grid(row=12,column=0,sticky="nw",padx=16,pady=7); notes=tk.Text(form,height=5,width=44,bd=1,relief="solid"); notes.grid(row=12,column=1,sticky="ew",padx=16,pady=7)
        def save():
            errors=[]
            from validation import validate_medication_record
            errors=validate_medication_record(entries["med"].get(),entries["resp"].get(),entries["severity"].get())
            if errors: self._status(" ".join(errors),"error"); return
            try:
                add_medication_record(self.current_user,entries["pid"].get(),entries["med"].get(),entries["resp"].get(),entries["reaction"].get(),entries["severity"].get(),entries["reason"].get(),notes.get("1.0","end"))
                self._route("_history"); self._status("Medication record saved successfully.","success")
            except Exception as exc: self._status(str(exc),"error")
        ttk.Button(form,text="Save record",style="Accent.TButton",command=save).grid(row=13,column=1,sticky="w",padx=16,pady=14)

    def _show_history(self):
        c=self._page("Patient History","Search medication history and see semantic safety states."); row=tk.Frame(c,bg=COLORS["bg"]); row.pack(fill="x",padx=34); e=ttk.Entry(row,width=24); e.pack(side="left"); med=ttk.Entry(row,width=22); med.pack(side="left",padx=8); ttk.Button(row,text="Search",style="Accent.TButton",command=lambda:self._history_results(e.get(),med.get())).pack(side="left")
        if self._is_patient(): e.insert(0,self._patient_id() or ""); e.config(state="disabled"); self._history_results(self._patient_id(),"")
        self._history_frame=tk.Frame(c,bg=COLORS["bg"]); self._history_frame.pack(fill="both",expand=True,padx=34,pady=10)
    def _history_results(self,pid,med):
        if not hasattr(self,"_history_frame"): return
        for w in self._history_frame.winfo_children(): w.destroy()
        try: recs=self._records(pid)
        except Exception as exc: tk.Label(self._history_frame,text=str(exc),bg=COLORS["bg"],fg=COLORS["red"]).pack(); return
        q=(med or "").lower(); recs=[r for r in recs if not q or q in str(r.get("medicine_name","")).lower()]
        for r in recs:
            rt=r.get("response_type") or "Unknown"; color=COLORS["red"] if rt in ("Allergy","Adverse reaction") else COLORS["amber"] if rt=="Ineffective" else COLORS["green"] if rt=="Effective" else COLORS["blue"]; soft=COLORS["red_soft"] if color==COLORS["red"] else COLORS["amber_soft"] if color==COLORS["amber"] else COLORS["green_soft"] if color==COLORS["green"] else COLORS["blue_soft"]
            f=tk.Frame(self._history_frame,bg="white",highlightbackground=COLORS["line"],highlightthickness=1); f.pack(fill="x",pady=4); tk.Label(f,text=f"{r.get('medicine_name')}  ·  {rt}",bg="white",fg=COLORS["ink"],font=("Segoe UI",10,"bold")).pack(side="left",padx=16,pady=12); self._pill(f,rt,color,soft).pack(side="right",padx=16,pady=9)

    def _show_ehr(self,pid=None):
        if self._role() not in {"owner","admin","doctor","staff"}: self._deny(); return
        c=self._page("Clinical EHR","Encounters, prescriptions and patient documents."); row=tk.Frame(c,bg=COLORS["bg"]); row.pack(fill="x",padx=34); e=ttk.Entry(row,width=24); e.pack(side="left"); e.insert(0,pid or ""); ttk.Button(row,text="Load",style="Accent.TButton",command=lambda:self._ehr_loaded(e.get())).pack(side="left",padx=8); self._ehr_body=tk.Frame(c,bg=COLORS["bg"]); self._ehr_body.pack(fill="both",expand=True,padx=34,pady=10)
        if pid: self._ehr_loaded(pid)
    def _ehr_loaded(self,pid):
        for w in self._ehr_body.winfo_children(): w.destroy()
        pid=pid.strip().upper()
        try: get_patient_by_id(self.current_user,pid); enc=list_encounters(self.current_user,pid); rx=list_prescriptions(self.current_user,pid); docs=list_attachments(self.current_user,pid)
        except Exception as exc: tk.Label(self._ehr_body,text=str(exc),bg=COLORS["bg"],fg=COLORS["red"]).pack(); return
        nb=ttk.Notebook(self._ehr_body); nb.pack(fill="both",expand=True); t1=ttk.Frame(nb); t2=ttk.Frame(nb); t3=ttk.Frame(nb); nb.add(t1,text="Encounters"); nb.add(t2,text="Prescriptions"); nb.add(t3,text="Documents")
        tree=ttk.Treeview(t1,columns=("id","date","type","complaint","diagnosis"),show="headings"); tree.pack(fill="both",expand=True,pady=5); self._tree_tags(tree)
        for k,h in [("id","ID"),("date","Date"),("type","Type"),("complaint","Chief complaint"),("diagnosis","Assessment")]: tree.heading(k,text=h); tree.column(k,width=140)
        for i,x in enumerate(enc):
            tag = "admin_deleted" if x.get("deleted_by_admin") else "archived" if x.get("is_archived") else ("zebra" if i % 2 else "active")
            tree.insert("","end",values=(x.get("encounter_id"),x.get("visit_date"),x.get("visit_type"),x.get("chief_complaint"),x.get("diagnoses")),tags=(tag,))
        self._tree_empty(t1, tree, "No encounters yet. Add the first clinical encounter for this patient.")
        if self._role() in {"owner","admin","doctor"}: ttk.Button(t1,text="＋ Add encounter",style="Accent.TButton",command=lambda:self._add_encounter(pid)).pack(anchor="w",pady=5)
        self._add_ehr_lifecycle_buttons(t1,tree,"encounter",pid)
        tr=ttk.Treeview(t2,columns=("id","med","dose","freq","dur","by"),show="headings"); tr.pack(fill="both",expand=True,pady=5); self._tree_tags(tr)
        for k,h in [("id","ID"),("med","Medicine"),("dose","Dose"),("freq","Frequency"),("dur","Duration"),("by","Prescribed by")]: tr.heading(k,text=h); tr.column(k,width=140)
        for i,x in enumerate(rx):
            tag = "admin_deleted" if x.get("deleted_by_admin") else "archived" if x.get("is_archived") else ("zebra" if i % 2 else "active")
            tr.insert("","end",values=(x.get("prescription_id"),x.get("medicine_name"),x.get("dosage"),x.get("frequency"),x.get("duration"),x.get("prescribed_by")),tags=(tag,))
        self._tree_empty(t2, tr, "No prescriptions yet. Add a prescription or scan a verified prescription.")
        ttk.Button(t2,text="＋ Add prescription",style="Accent.TButton",command=lambda:self._add_prescription(pid)).pack(anchor="w",pady=5)
        self._add_ehr_lifecycle_buttons(t2,tr,"prescription",pid)
        dt=ttk.Treeview(t3,columns=("id","name","type","by","date"),show="headings"); dt.pack(fill="both",expand=True,pady=5); self._tree_tags(dt)
        for k,h in [("id","ID"),("name","Document"),("type","Type"),("by","Uploaded by"),("date","Date")]: dt.heading(k,text=h); dt.column(k,width=160)
        for i,x in enumerate(docs):
            tag = "admin_deleted" if x.get("deleted_by_admin") else "archived" if x.get("is_archived") else ("zebra" if i % 2 else "active")
            dt.insert("","end",values=(x.get("attachment_id"),x.get("original_name"),x.get("mime_type"),x.get("uploaded_by"),x.get("created_at")),tags=(tag,))
        self._tree_empty(t3, dt, "No documents yet. Upload the first supporting document for this patient.")
        ttk.Button(t3,text="＋ Upload document",style="Accent.TButton",command=lambda:self._upload_doc(pid)).pack(anchor="w",pady=5)
        self._add_ehr_lifecycle_buttons(t3,dt,"document",pid)
    def _add_ehr_lifecycle_buttons(self,parent,tree,typ,pid):
        bar=tk.Frame(parent); bar.pack(fill="x",pady=5)
        def selected():
            sel=tree.selection(); return int(sel[0]) if sel else None
        def act(kind):
            rid=selected()
            if rid is None: self._status("Select a record first.","warning"); return
            try:
                if kind=="archive": archive_ehr_item(self.current_user,typ,rid)
                elif kind=="recover": recover_archived_ehr_item(self.current_user,typ,rid)
                elif kind=="delete":
                    from tkinter import simpledialog
                    if not messagebox.askyesno("Confirm admin delete","This will move the clinical record into the Admin-deleted recoverable state. Continue?",parent=self): return
                    confirm=simpledialog.askstring("Confirm admin delete","Type DELETE to confirm:",parent=self)
                    if confirm != "DELETE":
                        if confirm is not None: self._status("The record was not deleted.","warning")
                        return
                    pw=simpledialog.askstring("Recoverable delete","Enter your current account password:",show="*",parent=self)
                    if not pw:return
                    admin_delete_ehr_item(self.current_user,typ,rid,pw)
                elif kind=="owner_recover": recover_admin_deleted_ehr_item(self.current_user,typ,rid)
                elif kind=="permanent":
                    from tkinter import simpledialog
                    if not messagebox.askyesno("Permanent destruction","This permanently destroys the clinical record and cannot be undone. Continue?",parent=self): return
                    confirm=simpledialog.askstring("Permanent destruction","Type DELETE to confirm permanent destruction:",parent=self)
                    if confirm != "DELETE":
                        if confirm is not None: self._status("The record was not destroyed.", "warning")
                        return
                    pw=simpledialog.askstring("Permanent destruction","Enter current Owner password. This is irreversible:",show="*",parent=self)
                    if not pw:return
                    permanently_delete_ehr_item(self.current_user,typ,rid,pw)
                self._ehr_loaded(pid)
            except Exception as exc: self._status(str(exc), "error")
        if can_archive_records(self.current_user): ttk.Button(bar,text="Archive",command=lambda:act("archive")).pack(side="left",padx=2)
        if can_recover_archived_records(self.current_user): ttk.Button(bar,text="Recover archived",command=lambda:act("recover")).pack(side="left",padx=2)
        if can_admin_delete_records(self.current_user): ttk.Button(bar,text="Admin delete",command=lambda:act("delete")).pack(side="left",padx=2)
        if can_recover_admin_deleted_records(self.current_user): ttk.Button(bar,text="Owner recover",command=lambda:act("owner_recover")).pack(side="left",padx=2)
        if can_permanently_delete(self.current_user): ttk.Button(bar,text="Permanent destroy",command=lambda:act("permanent")).pack(side="left",padx=2)

    def _add_encounter(self,pid):
        w=tk.Toplevel(self); w.title("Add encounter"); w.geometry("500x430"); f=tk.Frame(w,bg="white",padx=20,pady=20); f.pack(fill="both",expand=True); es={}
        for i,(lab,key) in enumerate([("Visit date","date"),("Visit type","type"),("Chief complaint","complaint"),("Diagnoses / assessment","diag")]): tk.Label(f,text=lab,bg="white",fg=COLORS["ink"]).grid(row=i,column=0,sticky="w",pady=6); e=ttk.Entry(f,width=42); e.grid(row=i,column=1,pady=6); es[key]=e
        tk.Label(f,text="Visit notes",bg="white",fg=COLORS["ink"]).grid(row=4,column=0,sticky="nw",pady=6); n=tk.Text(f,height=7,width=42); n.grid(row=4,column=1,pady=6)
        def save():
            try: create_encounter(self.current_user,pid,es["date"].get(),es["type"].get(),es["complaint"].get(),n.get("1.0","end"),es["diag"].get()); w.destroy(); self._ehr_loaded(pid)
            except Exception as exc: self._status(str(exc), "error", parent=w)
        ttk.Button(f,text="Save",style="Accent.TButton",command=save).grid(row=5,column=1,sticky="w",pady=10)
    def _add_prescription(self,pid):
        w=tk.Toplevel(self); w.title("Add prescription"); w.geometry("520x390"); f=tk.Frame(w,bg="white",padx=20,pady=20); f.pack(fill="both",expand=True); es={}
        for i,(lab,key) in enumerate([("Medicine","med"),("Dosage","dose"),("Frequency","freq"),("Duration","dur"),("Instructions","inst")]): tk.Label(f,text=lab,bg="white",fg=COLORS["ink"]).grid(row=i,column=0,sticky="w",pady=6); e=ttk.Entry(f,width=44); e.grid(row=i,column=1,pady=6); es[key]=e
        def save():
            try: add_prescription(self.current_user,pid,es["med"].get(),es["dose"].get(),es["freq"].get(),es["dur"].get(),es["inst"].get()); w.destroy(); self._ehr_loaded(pid)
            except Exception as exc: self._status(str(exc), "error", parent=w)
        ttk.Button(f,text="Save",style="Accent.TButton",command=save).grid(row=5,column=1,sticky="w",pady=10)
    def _upload_doc(self,pid):
        path=filedialog.askopenfilename(parent=self,title="Choose document");
        if not path: return
        try: add_attachment(self.current_user,pid,path); self._ehr_loaded(pid)
        except Exception as exc: self._status(str(exc), "error")

    # --------------------------- prescription scan ---------------------------
    def _scan_prescription(self):
        if not self._is_patient() and self._role() not in {"owner","admin","doctor","staff"}:
            self._deny()
            return
        path=filedialog.askopenfilename(
            parent=self,
            title="Scan / upload prescription",
            filetypes=[
                ("Prescription images","*.png *.jpg *.jpeg *.webp"),
                ("PDF","*.pdf"),
                ("All files","*.*"),
            ],
        )
        if not path:
            return

        def extract():
            raw = ""
            try:
                ext = os.path.splitext(path)[1].lower()
                if ext in {".png",".jpg",".jpeg",".webp"} and Image is not None and pytesseract is not None:
                    with Image.open(path) as image:
                        raw = pytesseract.image_to_string(image)
                elif PdfReader is not None and path.lower().endswith(".pdf"):
                    raw = "\n".join((page.extract_text() or "") for page in PdfReader(path).pages)
            except Exception:
                # OCR/PDF extraction is assistive. A failure falls back to the
                # manual verification workflow rather than blocking the user.
                raw = ""
            return raw

        self._run_background(
            extract,
            lambda raw: self._prescription_review(path, raw),
            lambda exc: self._prescription_review(path, ""),
            title="Processing prescription…",
        )

    def _prescription_review(self,path,raw):
        w=tk.Toplevel(self); w.title("Prescription Scan — Verify before saving"); w.geometry("900x720"); w.transient(self); w.grab_set(); f=tk.Frame(w,bg=COLORS["bg"],padx=20,pady=18); f.pack(fill="both",expand=True)
        tk.Label(f,text="Prescription Scan",bg=COLORS["bg"],fg=COLORS["ink"],font=("Georgia",22,"bold")).pack(anchor="w")
        tk.Label(f,text="Draft extraction only. Verify every field against the original prescription before saving. Unclear fields are never silently guessed.",bg=COLORS["bg"],fg=COLORS["muted"],font=("Segoe UI",9),wraplength=820).pack(anchor="w",pady=(3,10))
        if not raw: tk.Label(f,text="🟠 OCR was unavailable or uncertain. Enter the prescription manually below.",bg=COLORS["amber_soft"],fg="#7A5200",font=("Segoe UI",9,"bold"),padx=10,pady=8).pack(fill="x",pady=(0,10))
        listbox=tk.Frame(f,bg="white",highlightbackground=COLORS["line"],highlightthickness=1); listbox.pack(fill="both",expand=True,pady=5)
        drafts=self._extract_med_drafts(raw)
        rows=[]
        headers=[("Medicine name","medicine"),("Strength / dosage","dosage"),("Frequency","frequency"),("Duration","duration"),("Route","route"),("Instructions","instructions")]
        def add_row(values=None):
            values=values or {}; row=tk.Frame(listbox,bg="white"); row.pack(fill="x",padx=8,pady=5); entries={}
            for j,(lab,key) in enumerate(headers):
                tk.Label(row,text=lab,bg="white",fg=COLORS["muted"],font=("Segoe UI",7,"bold")).grid(row=0,column=j,sticky="w")
                e=ttk.Entry(row,width=17); e.grid(row=1,column=j,padx=2,sticky="ew"); e.insert(0,values.get(key,"")); entries[key]=e
            rows.append(entries)
        for d in drafts: add_row(d)
        if not rows: add_row({})
        ttk.Button(f,text="＋ Add another medicine",style="Ghost.TButton",command=lambda:add_row({})).pack(anchor="w",pady=6)
        rawbox=tk.Text(f,height=6,font=("Consolas",8)); rawbox.pack(fill="x",pady=8); rawbox.insert("1.0",raw or "No OCR text available — compare directly with the source prescription."); rawbox.config(state="disabled")
        btn=tk.Frame(f,bg=COLORS["bg"]); btn.pack(fill="x")
        def save():
            try:
                pid=self._patient_id() if self._is_patient() else self._prompt_patient_id(w)
                if not pid: return
                clean=[]
                for r in rows:
                    d={k:e.get().strip() for _,k in headers for e in [r[k]]}
                    if not d["medicine"]: continue
                    clean.append(d)
                if not clean: raise RecordGuardError("Enter at least one medicine name.")
                if self._is_patient():
                    existing={x.get("medicine_name","").strip().lower() for x in list_personal_medications(self.current_user,pid)}
                    for d in clean:
                        if d["medicine"].lower() in existing and not messagebox.askyesno("Possible duplicate",f"{d['medicine']} already appears in your personal medicines. Create another entry?",parent=w):
                            continue
                        add_personal_medication(self.current_user,pid,d["medicine"],d["dosage"],d["frequency"],d["duration"],d["route"],d["instructions"],os.path.basename(path),"User verified")
                    add_attachment(self.current_user,pid,path)
                    w.destroy(); self._route("_medicines"); self._status(f"{len(clean)} verified personal medication draft(s) saved with the original prescription.","success"); return
                existing={x.get("medicine_name","").strip().lower() for x in list_prescriptions(self.current_user,pid)}
                for d in clean:
                    if d["medicine"].lower() in existing and not messagebox.askyesno("Possible duplicate",f"{d['medicine']} already appears in this patient's prescriptions. Create another prescription entry?",parent=w):
                        continue
                    add_prescription(self.current_user,pid,d["medicine"],d["dosage"],d["frequency"],d["duration"],d["instructions"])
                add_attachment(self.current_user,pid,path)
                msg="Prescription(s) saved." if self._role()!="staff" else "Prescription(s) saved as pending clinical verification."
                w.destroy(); self._show_ehr(pid); self._status(msg,"success")
            except Exception as exc: self._status(str(exc), "error", parent=w)
        ttk.Button(btn,text="Cancel",command=w.destroy).pack(side="right"); ttk.Button(btn,text="Verify & Save",style="Accent.TButton",command=save).pack(side="right",padx=8)

    def _extract_med_drafts(self,raw):
        if not raw: return []
        lines=[x.strip(" •\t") for x in raw.splitlines() if x.strip()]
        drafts=[]
        for line in lines:
            if re.search(r"prescription|patient|doctor|hospital|date[: ]",line,re.I): continue
            dm=re.search(r"\b(\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|mL|%))\b",line,re.I)
            fm=re.search(r"\b(once|twice|thrice|\d+\s*(?:times|x)\s*(?:daily|a day)|OD|BD|TDS|QID)\b",line,re.I)
            dur=re.search(r"\b(?:for\s*)?(\d+)\s*(days?|weeks?)\b",line,re.I)
            if dm or fm or dur:
                medicine=re.sub(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|mL|%)\b", "", line, flags=re.I)
                medicine=re.sub(r"\b(?:once|twice|thrice|\d+\s*(?:times|x)\s*(?:daily|a day)|OD|BD|TDS|QID)\b", "", medicine, flags=re.I)
                medicine=re.sub(r"\b(?:for\s*)?\d+\s*(?:days?|weeks?)\b", "", medicine, flags=re.I).strip(" -:.,")
                drafts.append({"medicine":medicine[:80],"dosage":dm.group(1) if dm else "","frequency":fm.group(1) if fm else "","duration":dur.group(0) if dur else "","route":"","instructions":""})
        return drafts[:12]

    def _prompt_patient_id(self,parent):
        from tkinter import simpledialog
        return simpledialog.askstring("Patient ID","Enter Patient ID for this prescription:",parent=parent)

    # --------------------------- admin/security ---------------------------
    def _show_users(self):
        if self._role() not in {"owner","admin"}: self._deny(); return
        c=self._page("User Management","Create login accounts separately from patient registration. Only authorised roles can provision privileged accounts.")
        guide=self._card(c,COLORS["teal_soft"])
        tk.Label(guide,text="Login account creation ≠ patient registration",bg=COLORS["teal_soft"],fg=COLORS["teal"],font=("Segoe UI",12,"bold")).pack(anchor="w",padx=18,pady=(12,3))
        tk.Label(guide,text="Register Patient creates the patient profile. This screen creates a login identity. Owner can create Admin, Doctor, Staff or a linked Patient login; Admin can create Doctor, Staff or a linked Patient login. Doctor and Staff cannot create privileged login accounts.",bg=COLORS["teal_soft"],fg="#356D66",font=("Segoe UI",9),wraplength=850,justify="left").pack(anchor="w",padx=18,pady=(0,10))
        form=self._card(c); fields={}
        for i,(lab,key) in enumerate([("Username","u"),("Full name","name"),("Password","p"),("Confirm password","cp")]): tk.Label(form,text=lab,bg="white",fg=COLORS["ink"]).grid(row=i,column=0,sticky="w",padx=14,pady=6); e=ttk.Entry(form,width=34,show="*" if key in ("p","cp") else ""); e.grid(row=i,column=1,padx=14,pady=6); fields[key]=e
        roles=["doctor","staff","patient"] if self._role()=="admin" else ["admin","doctor","staff","patient"]; rv=tk.StringVar(value=roles[0]); tk.Label(form,text="Role",bg="white",fg=COLORS["ink"]).grid(row=4,column=0,sticky="w",padx=14,pady=6); ttk.Combobox(form,textvariable=rv,values=roles,state="readonly",width=31).grid(row=4,column=1,padx=14,pady=6); pe=ttk.Entry(form,width=34); tk.Label(form,text="Patient ID (patient only)",bg="white",fg=COLORS["ink"]).grid(row=5,column=0,sticky="w",padx=14,pady=6); pe.grid(row=5,column=1,padx=14,pady=6)
        def create():
            try:
                if fields["p"].get()!=fields["cp"].get(): raise RecordGuardError("Passwords do not match.")
                create_new_user(self.current_user,fields["u"].get(),fields["p"].get(),rv.get(),fields["name"].get(),pe.get() or None); self._status("User account created successfully.", "success"); self._show_users()
            except Exception as exc: self._status(str(exc), "error")
        ttk.Button(form,text="Create account",style="Accent.TButton",command=create).grid(row=6,column=1,sticky="w",padx=14,pady=12)
        f=self._card(c); tree=ttk.Treeview(f,columns=("u","name","role","patient","org","status"),show="headings"); tree.pack(fill="both",expand=True,padx=10,pady=10)
        for k,h in [("u","Username"),("name","Full name"),("role","Role"),("patient","Patient ID"),("org","Organization"),("status","Status")]: tree.heading(k,text=h); tree.column(k,width=140)
        try:
            for u in list_users(self.current_user): tree.insert("","end",values=(u.get("username"),u.get("full_name"),u.get("role"),u.get("patient_id") or "—",u.get("organization_id") or "DEFAULT","Active" if u.get("active") else "Inactive"))
            self._tree_empty(f, tree, "No user accounts have been created yet.")
        except Exception as exc: tk.Label(f,text=str(exc),bg="white",fg=COLORS["red"]).pack(anchor="w",padx=18,pady=8)
        ttk.Button(f,text="Reset password for selected account",style="Ghost.TButton",command=lambda:self._reset_selected_user(tree)).pack(anchor="w",padx=18,pady=(0,14))

    def _reset_selected_user(self,tree):
        from tkinter import simpledialog
        sel=tree.selection()
        if not sel:
            self._status("Select a user account first.","warning"); return
        pw=simpledialog.askstring("Reset password","Enter a new temporary password (minimum 8 characters):",show="*",parent=self)
        if not pw: return
        confirm=simpledialog.askstring("Confirm password","Re-enter the new password:",show="*",parent=self)
        if pw!=confirm:
            self._status("Passwords do not match.","warning"); return
        try: reset_user_password(self.current_user,int(sel[0]),pw); self._status("Password reset successfully. Provide the new password through your approved recovery process.","success")
        except Exception as exc: self._status(str(exc),"error")

    def _show_security(self):
        if self._role() not in {"owner","admin","doctor"}: self._deny(); return
        c=self._page("Security & Records","Role-aware record lifecycle controls and audit visibility."); tk.Label(c,text="Record lifecycle",bg=COLORS["bg"],fg=COLORS["ink"],font=("Segoe UI",14,"bold")).pack(anchor="w",padx=34,pady=(5,7)); f=self._card(c)
        tk.Label(f,text="ACTIVE  →  ARCHIVED  →  ADMIN DELETED  →  OWNER PERMANENT DELETE",bg="white",fg=COLORS["ink"],font=("Segoe UI",10,"bold")).pack(anchor="w",padx=18,pady=(14,4)); tk.Label(f,text="Doctor: view/add/edit/archive. Admin: plus archived recovery and recoverable deletion. Owner: full lifecycle including Admin-deleted recovery and irreversible destruction. Staff: view/add. Patient: own active records only.",bg="white",fg=COLORS["muted"],font=("Segoe UI",8),wraplength=900,justify="left").pack(anchor="w",padx=18,pady=(0,14)); ttk.Button(f,text="Open record lifecycle manager",style="Accent.TButton",command=self._record_manager).pack(anchor="w",padx=18,pady=(0,14))
        if self._role() in {"owner","admin"}:
            ttk.Button(f,text="Review Patient-link requests",style="Ghost.TButton",command=self._show_link_requests).pack(anchor="w",padx=18,pady=(0,14))
        if self._role() in {"owner","admin"}:
            ttk.Button(f,text="Open system audit log",style="Ghost.TButton",command=lambda:self._route("_audit")).pack(anchor="w",padx=18,pady=(0,14))
        if self._role() in {"admin","owner"}:
            q=self._card(c); tk.Label(q,text="Correction requests",bg="white",fg=COLORS["ink"],font=("Segoe UI",12,"bold")).pack(anchor="w",padx=18,pady=(13,7));
            try: reqs=get_correction_requests(self.current_user)
            except Exception: reqs=[]
            for r in reqs[:20]:
                row=tk.Frame(q,bg="white"); row.pack(fill="x",padx=18,pady=4); tk.Label(row,text=f"#{r.get('request_id')} · {r.get('patient_id')} · {r.get('status')} · {r.get('reason')}",bg="white",fg=COLORS["muted"],font=("Segoe UI",8),wraplength=600,justify="left").pack(side="left")
                if r.get("status") not in {"Rejected","Resolved"}:
                    ttk.Button(row,text="Approve",command=lambda rid=r.get("request_id"):self._review_request(rid,"Approved")).pack(side="right",padx=2); ttk.Button(row,text="Reject",command=lambda rid=r.get("request_id"):self._review_request(rid,"Rejected")).pack(side="right",padx=2)
    def _show_link_requests(self):
        if self._role() not in {"owner","admin"}: self._deny(); return
        c=self._page("Patient Linking","Review requests to connect an existing Patient profile to a User Account."); f=self._card(c)
        try: reqs=list_patient_link_requests(self.current_user,"PENDING")
        except Exception as exc: self._status(str(exc),"error",c); return
        if not reqs:
            tk.Label(f,text="No pending Patient-link requests.",bg="white",fg=COLORS["muted"],font=("Segoe UI",10)).pack(padx=18,pady=20); return
        for r in reqs:
            row=tk.Frame(f,bg="white"); row.pack(fill="x",padx=16,pady=8)
            tk.Label(row,text=f"#{r['request_id']} · {r['username']} → {r['patient_id']} · {r['name']}",bg="white",fg=COLORS["ink"],font=("Segoe UI",10,"bold")).pack(side="left")
            ttk.Button(row,text="Approve",command=lambda rid=r['request_id']:self._review_link(rid,"APPROVED")).pack(side="right",padx=3)
            ttk.Button(row,text="Reject",command=lambda rid=r['request_id']:self._review_link(rid,"REJECTED")).pack(side="right",padx=3)

    def _review_link(self,rid,decision):
        from tkinter import simpledialog
        notes=simpledialog.askstring("Link review","Verification notes:",parent=self) or ""
        try: review_patient_link_request(self.current_user,rid,decision,notes); self._status(f"Link request {decision.lower()}.","success"); self._show_link_requests()
        except Exception as exc: self._status(str(exc),"error")

    def _review_request(self,rid,decision):
        from tkinter import simpledialog
        notes=simpledialog.askstring("Correction review","Review notes (optional):",parent=self) or ""
        try: review_correction_request(self.current_user,int(rid),decision,notes); self._status(f"Correction request {decision.lower()}.", "success"); self._show_security()
        except Exception as exc: self._status(str(exc), "error")

    def _show_audit_log(self):
        if self._role() not in {"owner","admin"}: self._deny(); return
        c=self._page("Audit Log","Structured, append-only system evidence. Table for quick review; event details for complete context.")
        filters=self._card(c); vars={k:tk.StringVar() for k in ("actor_id","actor_role","action","category","resource_type","result","patient_id")}
        labels=[("Actor ID","actor_id"),("Role","actor_role"),("Action","action"),("Category","category"),("Resource","resource_type"),("Result","result"),("Patient ID","patient_id")]
        for i,(lab,key) in enumerate(labels):
            tk.Label(filters,text=lab,bg="white",fg=COLORS["muted"],font=("Segoe UI",8,"bold")).grid(row=0,column=i,padx=5,pady=(10,2))
            ttk.Entry(filters,textvariable=vars[key],width=15).grid(row=1,column=i,padx=5,pady=(0,10))
        tree=ttk.Treeview(c,columns=("event","time","actor","role","action","category","resource","patient","result","corr"),show="headings",height=16)
        tree.pack(fill="both",expand=True,padx=12,pady=8); self._tree_tags(tree)
        for k,h,w in [("event","Event ID",120),("time","Timestamp",160),("actor","Actor",70),("role","Role",80),("action","Action",190),("category","Category",120),("resource","Resource",130),("patient","Patient",100),("result","Result",80),("corr","Correlation",130)]: tree.heading(k,text=h); tree.column(k,width=w,anchor="w")
        cache=[]
        def load():
            nonlocal cache
            try:
                cache=get_audit_log(self.current_user,{k:v.get() for k,v in vars.items()})
                for item in tree.get_children(): tree.delete(item)
                for i,r in enumerate(cache):
                    tree.insert("","end",iid=str(r.get("log_id")),values=(r.get("event_id"),r.get("timestamp"),r.get("actor_id"),r.get("actor_role"),r.get("action"),r.get("category"),r.get("resource_id") or r.get("resource_type") or "—",r.get("patient_id") or "—",r.get("result"),r.get("correlation_id") or "—"),tags=("zebra" if i%2 else "active",))
                self._tree_empty(c,tree,"No audit events match these filters.")
            except Exception as exc: self._status(str(exc),"error",c)
        ttk.Button(filters,text="Search",style="Accent.TButton",command=load).grid(row=1,column=len(labels),padx=8,pady=(0,10))
        def details(_=None):
            sel=tree.selection()
            if not sel: return
            row=next((x for x in cache if str(x.get("log_id"))==sel[0]),None)
            if not row: return
            w=tk.Toplevel(self); w.title(f"Audit event {row.get('event_id')}"); w.geometry("700x560"); text=tk.Text(w,wrap="word",font=("Consolas",10),bg="white",fg=COLORS["ink"],padx=14,pady=14); text.pack(fill="both",expand=True)
            text.insert("1.0",json.dumps(row,indent=2,ensure_ascii=False)); text.config(state="disabled")
        tree.bind("<Double-1>",details); load()

    def _record_manager(self):
        w=tk.Toplevel(self); w.title("Record lifecycle"); w.geometry("900x560"); tk.Label(w,text="Patient ID",font=("Segoe UI",9,"bold")).pack(anchor="w",padx=15,pady=7); e=ttk.Entry(w,width=24); e.pack(anchor="w",padx=15); tree=ttk.Treeview(w,columns=("id","med","resp","arch","del","date"),show="headings"); tree.pack(fill="both",expand=True,padx=15,pady=10); self._tree_tags(tree)
        for k,h in [("id","ID"),("med","Medicine"),("resp","Response"),("arch","Archived"),("del","Admin deleted"),("date","Date")]: tree.heading(k,text=h); tree.column(k,width=130)
        def load():
            for i in tree.get_children(): tree.delete(i)
            try:
                for r in get_medication_records_for_patient(e.get(),include_archived=True,include_admin_deleted=True,user=self.current_user):
                    tag = "admin_deleted" if r.get("deleted_by_admin") else "archived" if r.get("is_archived") else "active"
                    tree.insert("","end",iid=str(r["record_id"]),values=(r["record_id"],r["medicine_name"],r["response_type"],"Yes" if r["is_archived"] else "No","Yes" if r["deleted_by_admin"] else "No",r["record_date"]),tags=(tag,))
                self._tree_empty(w, tree, "No medication records found for this patient.")
            except Exception as exc: self._status(str(exc), "error", parent=w)
        ttk.Button(w,text="Load",style="Accent.TButton",command=load).pack(anchor="w",padx=15)
        actions=tk.Frame(w); actions.pack(fill="x",padx=15,pady=8)
        def sel():
            s=tree.selection(); return int(s[0]) if s else None
        def call(fn,*args):
            rid=sel();
            if rid is None: self._status("Select a record.","warning", parent=w); return
            try: fn(self.current_user,rid,*args); load()
            except Exception as exc: self._status(str(exc), "error", parent=w)
        if can_edit_records(self.current_user): ttk.Button(actions,text="Edit",command=lambda:self._edit_record_dialog(e.get(),sel(),w)).pack(side="left",padx=3)
        if can_archive_records(self.current_user): ttk.Button(actions,text="Archive",command=lambda:call(archive_medication_record)).pack(side="left",padx=3)
        if can_recover_archived_records(self.current_user): ttk.Button(actions,text="Recover archived",command=lambda:call(recover_archived_medication_record)).pack(side="left",padx=3)
        if can_admin_delete_records(self.current_user): ttk.Button(actions,text="Admin delete",command=lambda:self._admin_delete_dialog(sel(),w,load)).pack(side="left",padx=3)
        if can_recover_admin_deleted_records(self.current_user): ttk.Button(actions,text="Owner recover",command=lambda:call(recover_admin_deleted_medication_record)).pack(side="left",padx=3)
        if can_permanently_delete(self.current_user): ttk.Button(actions,text="Permanent destroy",command=lambda:self._permanent_delete_dialog(sel(),w,load)).pack(side="left",padx=3)
    def _edit_record_dialog(self,pid,rid,parent,load=None):
        if rid is None: self._status("Select a record.","warning", parent=parent); return
        recs=get_medication_records_for_patient(pid,include_archived=True,include_admin_deleted=True,user=self.current_user); r=next((x for x in recs if int(x["record_id"])==rid),None)
        if not r: return
        w=tk.Toplevel(parent); w.title("Edit record"); w.geometry("500x360"); f=tk.Frame(w,padx=20,pady=20); f.pack(fill="both",expand=True); es={}
        for i,(lab,key) in enumerate([("Medicine","medicine_name"),("Response","response_type"),("Reaction","reaction"),("Severity","severity"),("Reason","reason")]): tk.Label(f,text=lab).grid(row=i,column=0,sticky="w",pady=5); e=ttk.Entry(f,width=38); e.insert(0,r.get(key) or ""); e.grid(row=i,column=1,pady=5); es[key]=e
        def save():
            try: edit_medication_record(self.current_user,rid,es["medicine_name"].get(),es["response_type"].get(),es["reaction"].get(),es["severity"].get(),es["reason"].get(),r.get("notes") or ""); w.destroy(); load() if load else None
            except Exception as exc: self._status(str(exc), "error", parent=w)
        ttk.Button(f,text="Save",style="Accent.TButton",command=save).grid(row=5,column=1,sticky="w",pady=10)
    def _admin_delete_dialog(self,rid,parent,load):
        if rid is None: self._status("Select a record.","warning", parent=parent); return
        from tkinter import simpledialog
        if not messagebox.askyesno("Confirm admin delete","This will move the record into the Admin-deleted recoverable state. Continue?",parent=parent): return
        confirm=simpledialog.askstring("Confirm admin delete","Type DELETE to confirm:",parent=parent)
        if confirm != "DELETE":
            if confirm is not None: self._status("The record was not deleted.","warning",parent=parent)
            return
        pw=simpledialog.askstring("Admin delete","Enter your current account password:",show="*",parent=parent)
        if pw:
            try: admin_delete_medication_record(self.current_user,rid,pw); load()
            except Exception as exc: self._status(str(exc), "error", parent=parent)
    def _permanent_delete_dialog(self,rid,parent,load):
        if rid is None: self._status("Select a record.","warning", parent=parent); return
        from tkinter import simpledialog
        if not messagebox.askyesno("Permanent destruction","This permanently destroys the record and cannot be undone. Continue?",parent=parent): return
        confirm=simpledialog.askstring("Permanent destruction","Type DELETE to confirm permanent destruction:",parent=parent)
        if confirm != "DELETE":
            if confirm is not None: self._status("The record was not destroyed.", "warning", parent=parent)
            return
        pw=simpledialog.askstring("Permanent destruction","Enter your current Owner password:",show="*",parent=parent)
        if pw:
            try: permanently_delete_medication_record(self.current_user,rid,pw); load()
            except Exception as exc: self._status(str(exc), "error", parent=parent)

    def _show_backup(self):
        if self._role()!="owner": self._deny(); return
        c=self._page("Backup & Restore","Owner-only portable backup and restore of the database and attachments."); f=self._card(c); ttk.Button(f,text="Create .rgbackup",style="Accent.TButton",command=self._make_backup).pack(anchor="w",padx=18,pady=(15,7)); ttk.Button(f,text="Restore .rgbackup",command=self._restore_backup).pack(anchor="w",padx=18,pady=7); tk.Label(f,text="Backups require Owner authentication. Restore should be followed by an application restart.",bg="white",fg=COLORS["muted"],font=("Segoe UI",8)).pack(anchor="w",padx=18,pady=(3,14))
        try:
            hist=get_backup_history(self.current_user); tree=ttk.Treeview(c,columns=("id","path","by","date","action"),show="headings"); tree.pack(fill="both",expand=True,padx=34,pady=8)
            for k,h in [("id","ID"),("path","Path"),("by","Created by"),("date","Date"),("action","Action")]: tree.heading(k,text=h); tree.column(k,width=170)
            for x in hist: tree.insert("","end",values=(x.get("backup_id"),x.get("backup_path"),x.get("created_by"),x.get("created_at"),x.get("action")))
        except Exception: pass
    def _make_backup(self):
        path=filedialog.asksaveasfilename(parent=self,title="Create RecordGuard encrypted backup",defaultextension=".rgbackup",filetypes=[("RecordGuard backup","*.rgbackup")]);
        if not path: return
        from tkinter import simpledialog
        backup_pw=simpledialog.askstring("Backup encryption","Create a backup passphrase (minimum 8 characters). Store it separately; RecordGuard cannot recover it.",show="*",parent=self)
        if not backup_pw: return
        confirm=simpledialog.askstring("Confirm backup passphrase","Re-enter the backup passphrase:",show="*",parent=self)
        if confirm != backup_pw:
            self._status("Passphrases do not match. No backup was created.", "warning"); return
        try:
            backup_database(self.current_user,path,backup_pw); self._status("Encrypted backup created successfully.", "success"); self._show_backup()
        except Exception as exc: self._status(str(exc), "error")
    def _restore_backup(self):
        path=filedialog.askopenfilename(parent=self,title="Choose RecordGuard backup",filetypes=[("RecordGuard backup","*.rgbackup")]);
        if not path: return
        from tkinter import simpledialog
        pw=simpledialog.askstring("Restore","Enter current Owner password:",show="*",parent=self)
        if not pw: return
        backup_pw=simpledialog.askstring("Backup passphrase","Enter the backup encryption passphrase:",show="*",parent=self)
        if not backup_pw: return
        try: restore_database(self.current_user,path,pw,backup_pw); self._status("Backup restored. Restart RecordGuard before continuing.", "success")
        except Exception as exc: self._status(str(exc), "error")

    # --------------------------- family / delegated access ---------------------------
    def _render_family(self):
        role=self._role()
        if role not in {"owner","admin","patient"}:
            self._deny(); return
        pid=self._patient_id() if role=="patient" else None
        c=self._page("Family Access","Family relationships are separate from medical access. Every access grant is explicit and revocable.")
        intro=self._card(c,COLORS["teal_soft"])
        tk.Label(intro,text="Family relationship ≠ medical access",bg=COLORS["teal_soft"],fg=COLORS["teal"],font=("Segoe UI",12,"bold")).pack(anchor="w",padx=18,pady=(12,3))
        tk.Label(intro,text="A relationship such as Parent, Child, Guardian or Caregiver does not automatically unlock records. Medication, appointments, documents and full EHR access must be granted separately.",bg=COLORS["teal_soft"],fg="#356D66",font=("Segoe UI",9),wraplength=850,justify="left").pack(anchor="w",padx=18,pady=(0,12))
        if role in {"owner","admin"}:
            pick=self._card(c); tk.Label(pick,text="Patient",bg="white",fg=COLORS["ink"],font=("Segoe UI",9,"bold")).grid(row=0,column=0,padx=14,pady=10,sticky="w")
            pe=ttk.Entry(pick,width=24); pe.grid(row=0,column=1,padx=8,pady=10,sticky="w")
            ttk.Button(pick,text="Open",style="Accent.TButton",command=lambda:self._family_load(pe.get())).grid(row=0,column=2,padx=8,pady=10)
            tk.Label(pick,text="Enter a Patient ID to manage relationships and explicit delegated access.",bg="white",fg=COLORS["muted"],font=("Segoe UI",8)).grid(row=1,column=0,columnspan=3,padx=14,pady=(0,10),sticky="w")
        else:
            self._family_load(pid, container=c)

    def _family_load(self,pid,container=None):
        pid=str(pid or "").strip().upper()
        if not pid:
            self._status("Enter a Patient ID.","warning"); return
        try:
            get_patient_by_id(self.current_user,pid)
        except Exception as exc:
            self._status(str(exc),"error"); return
        c=container or self._workspace
        for w in list(getattr(c,"_family_sections",[])):
            if w.winfo_exists(): w.destroy()
        sections=[]
        c._family_sections=sections
        rel_card=self._card(c); sections.append(rel_card)
        tk.Label(rel_card,text="Family relationships",bg="white",fg=COLORS["ink"],font=("Segoe UI",12,"bold")).pack(anchor="w",padx=18,pady=(13,7))
        try: rels=list_family_relationships(self.current_user,pid)
        except Exception as exc: rels=[]; tk.Label(rel_card,text=str(exc),bg="white",fg=COLORS["red"]).pack(padx=18,pady=8)
        if rels:
            for rel in rels:
                row=tk.Frame(rel_card,bg="white"); row.pack(fill="x",padx=18,pady=4)
                tk.Label(row,text=f"{rel.get('related_name')} · {str(rel.get('relationship_type','')).replace('_',' ').title()}",bg="white",fg=COLORS["ink"],font=("Segoe UI",9,"bold")).pack(side="left")
                ttk.Button(row,text="Remove",command=lambda rid=rel.get("relationship_id"):self._family_remove(rid,pid)).pack(side="right")
                ttk.Button(row,text="Change",command=lambda rid=rel.get("relationship_id"):self._family_change(rid,pid)).pack(side="right",padx=4)
        else:
            tk.Label(rel_card,text="No family relationships have been recorded.",bg="white",fg=COLORS["muted"],font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=8)
        add=tk.Frame(rel_card,bg="white"); add.pack(fill="x",padx=18,pady=(6,14))
        related=ttk.Entry(add,width=22); related.pack(side="left")
        typ=ttk.Combobox(add,values=sorted(x.replace('_',' ').title() for x in {"spouse_partner","parent","child","guardian","dependent","sibling","caregiver","other"}),state="readonly",width=18); typ.pack(side="left",padx=6); typ.set("Caregiver")
        ttk.Button(add,text="Add relationship",style="Ghost.TButton",command=lambda:self._family_add(pid,related.get(),typ.get())).pack(side="left")

        access=self._card(c,COLORS["indigo_soft"]); sections.append(access)
        tk.Label(access,text="Explicit medical access",bg=COLORS["indigo_soft"],fg=COLORS["indigo_dark"],font=("Segoe UI",12,"bold")).pack(anchor="w",padx=18,pady=(13,4))
        users=[]
        try: users=[u for u in list_users(self.current_user) if u.get("active") and u.get("user_id")!=self.current_user.get("user_id")]
        except Exception: users=[]
        if users:
            form=tk.Frame(access,bg=COLORS["indigo_soft"]); form.pack(fill="x",padx=18,pady=7)
            labels=[f"{u.get('full_name') or u.get('username')} ({u.get('username')})" for u in users]
            cb=ttk.Combobox(form,values=labels,state="readonly",width=34); cb.pack(side="left")
            resource=ttk.Combobox(form,values=["medication","appointments","documents","ehr"],state="readonly",width=16); resource.pack(side="left",padx=6); resource.set("medication")
            perm=ttk.Combobox(form,values=["view","restrict"],state="readonly",width=12); perm.pack(side="left"); perm.set("view")
            def grant():
                i=cb.current()
                if i<0: self._status("Select a user.","warning"); return
                try: grant_family_access(self.current_user,pid,users[i]["user_id"],resource.get(),perm.get()); self._status("Family access grant saved.","success"); self._family_load(pid,c)
                except Exception as exc: self._status(str(exc),"error")
            ttk.Button(form,text="Grant",style="Accent.TButton",command=grant).pack(side="left",padx=6)
        try: grants=list_family_access(self.current_user,pid)
        except Exception: grants=[]
        for g in grants:
            row=tk.Frame(access,bg=COLORS["indigo_soft"]); row.pack(fill="x",padx=18,pady=3)
            text=f"{g.get('full_name') or g.get('username')} · {g.get('resource_type')} · {g.get('permission')} · {g.get('status')}"
            tk.Label(row,text=text,bg=COLORS["indigo_soft"],fg=COLORS["ink"],font=("Segoe UI",8)).pack(side="left")
            if g.get("status")=="ACTIVE": ttk.Button(row,text="Revoke",command=lambda gid=g.get("grant_id"):self._family_revoke(gid,pid,c)).pack(side="right")
        if not grants: tk.Label(access,text="No explicit family access grants.",bg=COLORS["indigo_soft"],fg=COLORS["muted"],font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=8)

    def _family_add(self,pid,related,typ):
        mapping={x.replace('_',' ').title():x for x in {"spouse_partner","parent","child","guardian","dependent","sibling","caregiver","other"}}
        try: create_family_relationship(self.current_user,pid,related,mapping.get(typ,typ.lower().replace(' ','_'))); self._status("Family relationship added.","success"); self._family_load(pid)
        except Exception as exc: self._status(str(exc),"error")
    def _family_change(self,rid,pid):
        from tkinter import simpledialog
        typ=simpledialog.askstring("Change relationship","Enter one of: " + ", ".join(sorted({"spouse_partner","parent","child","guardian","dependent","sibling","caregiver","other"})),parent=self)
        if typ:
            try: change_family_relationship(self.current_user,rid,typ.lower().replace(' ','_')); self._status("Relationship updated.","success"); self._family_load(pid)
            except Exception as exc: self._status(str(exc),"error")
    def _family_remove(self,rid,pid):
        if not messagebox.askyesno("Remove relationship","Remove this family relationship?",parent=self): return
        try: remove_family_relationship(self.current_user,rid); self._status("Family relationship removed.","success"); self._family_load(pid)
        except Exception as exc: self._status(str(exc),"error")
    def _family_revoke(self,gid,pid,c):
        if not messagebox.askyesno("Revoke access","Revoke this family access grant?",parent=self): return
        try: revoke_family_access(self.current_user,gid); self._status("Family access revoked.","success"); self._family_load(pid,c)
        except Exception as exc: self._status(str(exc),"error")

    # --------------------------- profile/settings/correction ---------------------------
    def _show_profile(self):
        c=self._page("Profile","Your RecordGuard account information."); f=self._card(c); tk.Label(f,text=self.current_user.get("full_name") or self.current_user.get("username"),bg="white",fg=COLORS["ink"],font=("Segoe UI",17,"bold")).pack(anchor="w",padx=18,pady=(15,3)); tk.Label(f,text=f"Username: {self.current_user.get('username')}  ·  Role: {self._role().title()}",bg="white",fg=COLORS["muted"],font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=(0,14));
        if self._role() in {"user", "patient"}:
            linked=self._patient_id()
            tk.Label(f,text=f"Linked Patient ID: {linked or 'Not linked'}",bg="white",fg=COLORS["teal"],font=("Segoe UI",9,"bold")).pack(anchor="w",padx=18,pady=(0,8))
            if not linked:
                row=tk.Frame(f,bg="white"); row.pack(fill="x",padx=18,pady=(0,14))
                ttk.Button(row,text="Link existing Patient record",style="Accent.TButton",command=self._request_patient_link).pack(side="left")
            else:
                ttk.Button(f,text="Unlink Patient record",style="Ghost.TButton",command=self._unlink_my_patient).pack(anchor="w",padx=18,pady=(0,14))
    def _show_settings(self):
        c=self._page("Settings","Application preferences and account-safe display information."); f=self._card(c,COLORS["indigo_soft"]); tk.Label(f,text="Appearance",bg=COLORS["indigo_soft"],fg=COLORS["indigo_dark"],font=("Segoe UI",12,"bold")).pack(anchor="w",padx=18,pady=(14,3)); tk.Label(f,text="RecordGuard currently uses a consistent light clinical theme. User-selectable appearance preferences are not yet persisted.",bg=COLORS["indigo_soft"],fg="#625E86",font=("Segoe UI",9),wraplength=850,justify="left").pack(anchor="w",padx=18,pady=(0,12));
    def _correction_dialog(self):
        pid=self._patient_id(); recs=self._records(pid); from tkinter import simpledialog
        if not recs: self._status("There are no active medication records to request correction for.","info"); return
        labels=[f"{r.get('record_id')} — {r.get('medicine_name')}" for r in recs]; w=tk.Toplevel(self); w.title("Request correction"); w.geometry("500x300"); f=tk.Frame(w,bg="white",padx=20,pady=20); f.pack(fill="both",expand=True); tk.Label(f,text="Record",bg="white").pack(anchor="w"); cb=ttk.Combobox(f,values=labels,state="readonly",width=50); cb.pack(anchor="w",pady=7); tk.Label(f,text="What needs correction?",bg="white").pack(anchor="w"); t=tk.Text(f,height=7,width=50); t.pack(pady=7)
        def submit():
            try: request_record_correction(self.current_user,pid,int(cb.get().split(" — ")[0]),t.get("1.0","end")); w.destroy(); self._status("Correction request submitted.", "success")
            except Exception as exc: self._status(str(exc), "error", parent=w)
        ttk.Button(f,text="Submit",style="Accent.TButton",command=submit).pack(anchor="w")

    # --------------------------- utility / errors ---------------------------
    def _request_patient_link(self):
        from tkinter import simpledialog
        pid=simpledialog.askstring("Link Patient record","Enter the existing Patient ID:",parent=self)
        if not pid: return
        reason=simpledialog.askstring("Verification context","Briefly describe the authorization/verification basis:",parent=self) or ""
        try:
            rid=request_patient_link(self.current_user,pid,reason); self._status(f"Link request #{rid} submitted for authorization.","success"); self._show_profile()
        except Exception as exc: self._status(str(exc),"error")

    def _unlink_my_patient(self):
        from tkinter import simpledialog
        pw=simpledialog.askstring("Confirm unlink","Enter your account password:",show="*",parent=self)
        if not pw: return
        try:
            unlink_patient_account(self.current_user,pw); self.current_user=authenticate_user(self.current_user.get("username"),pw); self._status("Patient link removed. Medical records remain with the Patient profile.","success"); self._show_profile()
        except Exception as exc: self._status(str(exc),"error")

    def _deny(self): self._status("Your role does not have permission to perform this action.", "warning")


def launch_app():
    RecordGuardApp().mainloop()

if __name__ == "__main__": launch_app()