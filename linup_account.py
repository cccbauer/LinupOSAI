"""Account + sync UI for Linup (mixin for LinupApp).

Needs from the host class: self.page, self.db_path, self._set_view(),
self.show_main_menu(), self.show_load_investments().
"""
import asyncio
import os
import re
import time

import flet as ft

import linup_cloud
import linup_sync

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_AUTO_SYNC_MIN_GAP = 30  # seconds between automatic syncs


class AccountMixin:
    # ── setup ─────────────────────────────────────────────────────────
    def init_cloud(self):
        """Call after init_db(). Safe when the cloud isn't configured."""
        self.cloud_auth = None
        self.cloud_store = None
        self._sync_busy = False
        self._last_sync = 0.0
        self.sync_status = ""
        self.offline_mode = False
        if not getattr(self, "db_path", None):
            return
        try:
            linup_sync.ensure_sync_schema(self.db_path)
        except Exception as ex:
            print(f"sync schema warning: {ex}")
            return
        cfg = linup_cloud.load_config()
        if cfg:
            sess = os.path.join(os.path.dirname(self.db_path), "auth.json")
            self.cloud_auth = linup_cloud.CloudAuth(cfg[0], cfg[1], sess)
            self.cloud_store = linup_cloud.SupabaseStore(self.cloud_auth)

    @property
    def cloud_enabled(self):
        return self.cloud_auth is not None

    # ── sync ──────────────────────────────────────────────────────────
    async def _run_sync(self, force=False):
        """Two-way sync in a worker thread. Returns the summary or None."""
        if not (self.cloud_enabled and self.cloud_auth.signed_in) or self._sync_busy:
            return None
        if not force and time.time() - self._last_sync < _AUTO_SYNC_MIN_GAP:
            return None
        self._sync_busy = True
        self.sync_status = "Syncing…"
        loop = asyncio.get_running_loop()
        try:
            res = await loop.run_in_executor(
                None, lambda: linup_sync.SyncEngine(self.db_path, self.cloud_store).sync())
            self._last_sync = time.time()
            self.sync_status = "Synced " + time.strftime("%H:%M")
            return res
        except linup_cloud.CloudError as ex:
            self.sync_status = f"Sync failed: {ex}"
        except Exception as ex:  # never let sync break the app
            self.sync_status = f"Sync failed: {ex}"
        finally:
            self._sync_busy = False
        return None

    async def _sync_then_refresh_menu(self, force=False):
        res = await self._run_sync(force=force)
        # redraw only if a sync ran and the user is still looking at the menu
        if res is not None and self.root.content is getattr(self, "_menu_container", None):
            self.show_main_menu()
        return res

    # ── account screen ────────────────────────────────────────────────
    def show_account_screen(self, e=None, notice=""):
        email_f = ft.TextField(label="Email", width=300, height=50,
                               bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                               keyboard_type=ft.KeyboardType.EMAIL)
        pw_f = ft.TextField(label="Password (min 8 chars)", width=300, height=50,
                            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                            password=True, can_reveal_password=True)
        msg = ft.Text(notice, color='#f1c40f', size=13, width=300,
                      text_align=ft.TextAlign.CENTER)
        busy = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)

        def validate():
            em = (email_f.value or "").strip().lower()
            if not _EMAIL_RE.match(em):
                msg.value, msg.color = "Enter a valid email address.", '#ff6b6b'
                self.page.update()
                return None
            return em

        async def _do(kind):
            em = validate()
            if em is None:
                return
            pw = pw_f.value or ""
            if kind != "reset" and len(pw) < 8:
                msg.value, msg.color = "Password must be at least 8 characters.", '#ff6b6b'
                self.page.update()
                return
            busy.visible = True
            msg.value = ""
            self.page.update()
            loop = asyncio.get_running_loop()
            try:
                if kind == "in":
                    await loop.run_in_executor(None, self.cloud_auth.sign_in, em, pw)
                elif kind == "up":
                    r = await loop.run_in_executor(None, self.cloud_auth.sign_up, em, pw)
                    if r == "confirm_email":
                        busy.visible = False
                        msg.value = ("Account created. Check your email and click the "
                                     "verification link, then sign in.")
                        msg.color = '#2ecc71'
                        self.page.update()
                        return
                else:
                    await loop.run_in_executor(None, self.cloud_auth.reset_password, em)
                    busy.visible = False
                    msg.value = "If that account exists, a reset link was emailed."
                    msg.color = '#2ecc71'
                    self.page.update()
                    return
            except linup_cloud.CloudError as ex:
                busy.visible = False
                msg.value, msg.color = str(ex), '#ff6b6b'
                self.page.update()
                return
            busy.visible = False
            await self._after_sign_in()

        def on(kind):
            return lambda ev: self.page.run_task(_do, kind)

        def offline(ev):
            self.offline_mode = True
            self.show_main_menu()

        self._set_view(ft.Container(
            bgcolor='#1a1a1a', expand=True, padding=20,
            content=ft.Column(
                expand=True, scroll=ft.ScrollMode.AUTO,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Linup", color='#3498db', size=42, weight=ft.FontWeight.BOLD),
                    ft.Text("Sign in to keep your investments on all your devices",
                            color='#aaaaaa', size=13, width=300,
                            text_align=ft.TextAlign.CENTER),
                    ft.Container(height=20), email_f, pw_f, msg, busy,
                    ft.ElevatedButton("SIGN IN", on_click=on("in"), width=300, height=48,
                                      style=ft.ButtonStyle(bgcolor='#2980b9',
                                                           color=ft.Colors.WHITE)),
                    ft.ElevatedButton("CREATE ACCOUNT", on_click=on("up"), width=300,
                                      height=48,
                                      style=ft.ButtonStyle(bgcolor='#27ae60',
                                                           color=ft.Colors.WHITE)),
                    ft.TextButton("Forgot password?", on_click=on("reset")),
                    ft.TextButton("Continue offline (no sync)", on_click=offline),
                ],
            ),
        ))

    async def _after_sign_in(self):
        """Handle device ownership, then first sync, then menu."""
        uid = self.cloud_auth.user_id
        owner = linup_sync.get_owner(self.db_path)
        if owner and owner != uid and linup_sync.has_local_investments(self.db_path):
            self._confirm_account_switch(uid)
            return
        linup_sync.set_owner(self.db_path, uid)
        self._set_view(ft.Container(
            bgcolor='#1a1a1a', expand=True,
            content=ft.Column(
                expand=True, alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[ft.ProgressRing(color='#3498db'),
                          ft.Text("Syncing your investments…", color='#aaaaaa')])))
        await self._run_sync(force=True)
        self.show_main_menu()

    def _confirm_account_switch(self, new_uid):
        async def _proceed(ev):
            linup_sync.stash_and_clear_local(self.db_path)
            linup_sync.set_owner(self.db_path, new_uid)
            await self._after_sign_in()

        def _cancel(ev):
            self.cloud_auth.sign_out()
            self.show_account_screen()

        self._set_view(ft.Container(
            bgcolor='#1a1a1a', expand=True, padding=24,
            content=ft.Column(
                expand=True, alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Different account", size=26, color='#f1c40f',
                            weight=ft.FontWeight.BOLD),
                    ft.Text("This device holds investments from another account. "
                            "They will be backed up to the stash folder and removed "
                            "from the app, then your account's investments will load.",
                            color='#dddddd', width=320, text_align=ft.TextAlign.CENTER),
                    ft.Container(height=16),
                    ft.ElevatedButton("BACK UP & CONTINUE",
                                      on_click=lambda ev: self.page.run_task(_proceed, ev),
                                      width=300, height=48,
                                      style=ft.ButtonStyle(bgcolor='#c0392b',
                                                           color=ft.Colors.WHITE)),
                    ft.TextButton("Cancel", on_click=_cancel),
                ],
            ),
        ))

    # ── main-menu widget ──────────────────────────────────────────────
    def account_menu_controls(self):
        """Controls to append to the main menu."""
        if not self.cloud_enabled:
            return []
        if not self.cloud_auth.signed_in:
            return [
                ft.Container(height=24),
                ft.TextButton("Sign in to sync across devices",
                              on_click=self.show_account_screen),
            ]

        def sync_now(ev):
            self.page.run_task(self._sync_then_refresh_menu, True)

        def sign_out(ev):
            self.cloud_auth.sign_out()
            self.show_account_screen()

        return [
            ft.Container(height=24),
            ft.Text(self.cloud_auth.email, color='#aaaaaa', size=12),
            ft.Text(self.sync_status or "", color='#888888', size=11),
            ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[
                ft.TextButton("Sync now", on_click=sync_now),
                ft.TextButton("Sign out", on_click=sign_out),
            ]),
        ]
