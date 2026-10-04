import sys
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import messagebox
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from um import dragon_i18n as i18n

try:
    _probe = tk.Tk()
    _probe.destroy()
    HAVE_DISPLAY = True
except tk.TclError:
    HAVE_DISPLAY = False


def texts(widget):
    """All visible texts (labels, buttons, radio/check buttons, tab-like frames) below widget."""
    found = []
    for child in widget.winfo_children():
        try:
            text = child.cget('text')
            if text:
                found.append(str(text))
        except tk.TclError:
            pass
        found.extend(texts(child))
    return found


@unittest.skipUnless(HAVE_DISPLAY, 'needs a display')
class GuiSmokeTests(unittest.TestCase):
    def setUp(self):
        from um.gui.app import DragonApp
        self.patches = [patch.object(DragonApp, '_load_settings', return_value={'language': 'en', 'theme': 'light'}),
                        patch.object(DragonApp, 'save_settings'),
                        patch('um.dragon_custom_targets.list_ids', return_value=[]),
                        patch.object(messagebox, 'askyesnocancel', return_value=None),
                        patch.object(messagebox, 'showinfo'), patch.object(messagebox, 'showerror'),
                        patch.object(messagebox, 'showwarning')]
        for p in self.patches:
            p.start()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = DragonApp(self.root)

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        for p in self.patches:
            p.stop()
        i18n.set_language('en')

    def pump(self, seconds=0.2):
        end = time.time() + seconds
        while time.time() < end:
            self.root.update()
            time.sleep(0.02)

    def test_starts_on_other_with_no_character_and_a_helpful_message(self):
        self.assertEqual(self.app.source_kind.get(), 'other')
        self.assertEqual(self.app.target_id.get(), '')
        page = self.app.pages['convert']
        self.assertIn('No saved character', page.info.get())
        page.start_convert()  # nothing chosen: a message, not a crash
        messagebox.showinfo.assert_called()

    def test_window_and_pages_are_not_labelled_lost_judgment_beta(self):
        self.assertEqual(self.root.title(), 'VRMDragonTool')
        # folder paths shown in the window (this checkout may itself be called '(Beta)') are not labels
        everything = ' '.join(t for t in texts(self.root) if '\' not in t and '/' not in t)
        self.assertNotIn('β', everything)
        self.assertNotIn('Beta', everything)

    def test_every_page_can_be_shown_in_both_languages_and_themes(self):
        for language in ('en', 'ja'):
            for mode in ('light', 'dark'):
                self.app.language.set(language)
                self.app.theme.set(mode)
                self.app.change_appearance('theme', 'x')
                self.assertEqual(i18n.get_language(), language)
                for key in self.app.pages:
                    self.app.show_page(key)
                    self.root.update()
                self.assertIn(self.app.nav['convert'].cget('text'), ('Convert', '変換'))

    def test_japanese_labels_are_actually_japanese(self):
        self.app.language.set('ja')
        self.app.change_appearance('language', 'en')
        text = ' '.join(texts(self.root))
        for word in ('変換', '詳細ツール', 'セットアップ', '設定', 'キャラクター'):
            self.assertIn(word, text)
        for english in ('Advanced tools', 'Storage & logs', 'Saved characters', 'Parallel Blender jobs'):
            self.assertNotIn(english, text)

    def test_switching_to_the_builtin_characters_shows_their_controls(self):
        page = self.app.pages['convert']
        self.app.source_kind.set('builtin')
        page.on_kind_change()
        self.pump()
        self.assertEqual(page.current_target(), self.app.builtin_target.get())
        self.assertTrue(page.builtin.winfo_manager())
        self.assertFalse(page.other.winfo_manager())

    def test_busy_tasks_disable_the_convert_button_and_block_appearance_changes(self):
        page = self.app.pages['convert']
        done = []
        release = threading.Event()
        self.app.tasks.run(lambda progress: (release.wait(10), 'ok')[1], on_done=done.append)
        self.assertEqual(str(page.convert_button.cget('state')), 'disabled')
        self.app.language.set('ja')
        self.app.change_appearance('language', 'en')
        self.assertEqual(self.app.language.get(), 'en')  # refused while busy, reverted
        release.set()
        for _ in range(100):
            self.pump(0.1)
            if done:
                break
        self.assertEqual(done, ['ok'])
        self.assertEqual(str(page.convert_button.cget('state')), 'normal')

    def test_a_failing_task_reports_instead_of_crashing(self):
        errors = []

        def boom(progress):
            raise ValueError('boom')
        self.app.tasks.run(boom, on_error=errors.append, label='Test task')
        self.pump(0.4)
        self.assertEqual([str(e) for e in errors], ['boom'])
        self.assertFalse(self.app.tasks.busy)


if __name__ == '__main__':
    unittest.main()
