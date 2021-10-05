"""
MIT License

Copyright (c) 2021 Aaron Fu Lei

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# standard
import re
import string

# sublime
import sublime
import sublime_plugin


# --- flags -------------------------------------------------------------------

SB = sublime.CLASS_WORD_START | sublime.CLASS_SUB_WORD_START
SE = sublime.CLASS_WORD_END | sublime.CLASS_SUB_WORD_END


# --- globals -----------------------------------------------------------------

# g_swap_center is a dict that keeps track of the region to swap with for each
# view. The key is a view id. The value is a (region, text) tuple.
g_swap_center = {}


# --- utilities ---------------------------------------------------------------

def _abridge(s, maxlen=20):
    if len(s) <= maxlen:
        return s
    else:
        half = max(maxlen // 2 - 2, 0)
        return s[:half] + " .. " + s[-half:]


def _classify(c):
    if c in "_\n":
        return c
    if c in string.ascii_lowercase:
        return "a"
    if c in string.ascii_uppercase:
        return "A"
    if c in string.digits:
        return "1"
    if c in string.punctuation:
        return "."
    if c in string.whitespace:
        return " "
    return "?"


def _expand(view, subword):
    if subword:
        view.run_command("expand_selection_to_subword")
    else:
        view.run_command("expand_selection", {"to": "word"})


def _reset_swap(view):
    view.erase_status("expand_swap")
    view.erase_regions("expand_swap")
    g_swap_center[view.id()] = None


def is_subword_begin(view, point):
    return bool(view.classify(point) & SB)


def is_subword_end(view, point):
    return bool(view.classify(point) & SE)


def prev_subword_begin(view, point):
    return view.find_by_class(point, forward=False, classes=SB)


def next_subword_end(view, point):
    return view.find_by_class(point, forward=True, classes=SE)


# --- expand selection to subword ---------------------------------------------

class ExpandSelectionToSubwordCommand(sublime_plugin.TextCommand):
    def run(self, edit, prefer_forwards=True):
        old_sel = list(self.view.sel())
        new_sel = []
        for region in old_sel:
            self.view.sel().clear()
            self.view.sel().add(region)
            reg = self.view.sel()[0]
            b = reg.begin()
            e = reg.end()
            isb = is_subword_begin(self.view, b)
            if isb:
                sb = b
            else:
                sb = prev_subword_begin(self.view, b)
            ise = is_subword_end(self.view, e)
            if ise:
                se = e
            else:
                se = next_subword_end(self.view, e)
            if b == e and isb and ise:
                substr = self.view.substr(sublime.Region(b-1, b+1))
                if len(substr) == 2:
                    kind = _classify(substr[0]) + _classify(substr[1])
                    extend_forwards = True
                    if kind in {"aA", "1A"}:
                        # e.g. Text|Command --> Text[Command] or [Text]Command
                        extend_forwards = prefer_forwards
                    elif kind[1] == "_":
                        # e.g. SUB|_WORD --> [SUB]_WORD
                        extend_forwards = False
                    if extend_forwards:
                        se = next_subword_end(self.view, e)
                    else:
                        sb = prev_subword_begin(self.view, b)
            sr = sublime.Region(sb, se)
            new_sel.append(sr)
        self.view.sel().clear()
        self.view.sel().add_all(new_sel)


# --- listener ----------------------------------------------------------------

class ExpandSwapListener(sublime_plugin.ViewEventListener):
    def on_modified_async(self):
        _reset_swap(self.view)

    def on_post_text_command(self, command_name, args):
        if command_name not in {"drag_select", "move", "move_to",
                                "expand_swap_word", "expand_swap_subword"}:
            _reset_swap(self.view)


# --- base commands -----------------------------------------------------------

class ExpandCutCommand(sublime_plugin.TextCommand):
    def run(self, edit, subword=False):
        _expand(self.view, subword)
        self.view.run_command("cut")


class ExpandCopyCommand(sublime_plugin.TextCommand):
    def run(self, edit, subword=False):
        orig_sel = list(self.view.sel())
        _expand(self.view, subword)
        self.view.run_command("copy")
        expa_sel = list(self.view.sel())
        self.view.add_regions("expand_copy", expa_sel, scope="string")
        sublime.set_timeout_async(
            lambda: self.view.erase_regions("expand_copy"), 100)
        sublime.set_timeout_async(
            lambda: self.view.add_regions(
                "expand_copy",
                expa_sel,
                scope="string"), 200)
        sublime.set_timeout_async(
            lambda: self.view.erase_regions("expand_copy"), 300)
        self.view.sel().clear()
        self.view.sel().add_all(orig_sel)


class ExpandPasteCommand(sublime_plugin.TextCommand):
    def run(self, edit, subword=False):
        _expand(self.view, subword)
        self.view.run_command("paste")


class ExpandDeleteCommand(sublime_plugin.TextCommand):
    def run(self, edit, subword=False):
        _expand(self.view, subword)
        self.view.run_command("left_delete")


class ExpandDisplaceCommand(sublime_plugin.TextCommand):
    def run(self, edit, subword=False):
        # --- WRONG -------------
        # if not self.view.sel():
        # -----------------------
        # self.view.sel() evaluates to True even if there are no selections
        if len(self.view.sel()) == 0:
            return
        _expand(self.view, subword)
        orig_word = self.view.substr(self.view.sel()[-1])
        self.view.run_command("paste")
        sublime.set_clipboard(orig_word)


class ExpandSwapCommand(sublime_plugin.TextCommand):
    def run(self, edit, subword=False):
        if len(self.view.sel()) != 1:
            self.view.set_status("expand_swap", "Can't Swap")
            sublime.set_timeout_async(
                lambda: self.view.erase_status("expand_swap"), 4000)
            return
        vid = self.view.id()
        g_swap_center.setdefault(vid, None)
        if g_swap_center[vid] is None:
            old_sel = list(self.view.sel())
            _expand(self.view, subword)
            region = self.view.sel()[0]
            line = self.view.rowcol(region.begin())[0] + 1
            text = self.view.substr(region)
            abridged = _abridge(text)
            g_swap_center[vid] = (region, text)
            self.view.sel().clear()
            self.view.sel().add_all(old_sel)
            self.view.set_status(
                "expand_swap",
                "Swapping \"{}\" @ Line {}".format(abridged, line))
            self.view.add_regions("expand_swap", [region], scope="string")
        else:
            _expand(self.view, subword)
            swap_region, swap_text = g_swap_center[vid]
            curr_text = self.view.substr(self.view.sel()[0])
            self.view.replace(edit, swap_region, curr_text)
            self.view.replace(edit, self.view.sel()[0], swap_text)
            _reset_swap(self.view)


class CancelSwapCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        _reset_swap(self.view)


# --- derived commands --------------------------------------------------------

class ExpandCutWordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_cut")


class ExpandCutSubwordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_cut", {"subword": True})


class ExpandCopyWordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_copy")


class ExpandCopySubwordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_copy", {"subword": True})


class ExpandPasteWordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_paste")


class ExpandPasteSubwordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_paste", {"subword": True})


class ExpandDeleteWordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_delete")


class ExpandDeleteSubwordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_delete", {"subword": True})


class ExpandDisplaceWordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_displace")


class ExpandDisplaceSubwordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_displace", {"subword": True})


class ExpandSwapWordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_swap")


class ExpandSwapSubwordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("expand_swap", {"subword": True})


# --- injection ---------------------------------------------------------------

# *** All the code below is based on Default/paste_from_history.py ***

class ClipboardHistory():
    """
    Stores the current paste history
    """
    LIST_LIMIT = 15

    def __init__(self):
        self.storage = []

    def push_text(self, text):
        if not text:
            return
        DISPLAY_LEN = 45
        # create a display text out of the text
        display_text = re.sub(r"[\n]", "", text)
        # trim all starting space/tabs
        display_text = re.sub(r"^[\t\s]+", "", display_text)
        display_text = ((display_text[:DISPLAY_LEN] + "...")
                        if len(display_text) > DISPLAY_LEN else display_text)
        self.del_duplicate(text)
        self.storage.insert(0, (display_text, text))
        if len(self.storage) > self.LIST_LIMIT:
            del self.storage[self.LIST_LIMIT:]

    def get(self):
        return self.storage

    def del_duplicate(self, text):
        # remove all dups
        self.storage = [s for s in self.storage if s[1] != text]

    def empty(self):
        return len(self.storage) == 0


g_clipboard_history = ClipboardHistory()


class ClipboardHistoryUpdater(sublime_plugin.EventListener):
    """
    Listens on the sublime text events and push the clipboard content into the
    ClipboardHistory object
    """
    def on_post_text_command(self, view, name, args):
        if view.settings().get("is_widget"):
            return
        # ----- MODIFIED ------------------------------------------------------
        # if name == "copy" or name == "cut":
        if name in {"copy", "cut", "expand_cut_word", "expand_cut_subword",
                    "expand_copy_word", "expand_copy_subword",
                    "expand_displace_word", "expand_displace_subword"}:
            try:
                # use get_clipboard_async() when possible
                sublime.get_clipboard_async(
                    lambda x: g_clipboard_history.push_text(x))
            except AttributeError:
                g_clipboard_history.push_text(sublime.get_clipboard())
        # ---------------------------------------------------------------------


class PasteFromHistoryCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if self.view.settings().get("is_widget"):
            return
        # provide paste choices
        paste_list = g_clipboard_history.get()
        keys = [x[0] for x in paste_list]
        self.view.show_popup_menu(
            keys, lambda choice_index: self.paste_choice(choice_index))

    def is_enabled(self):
        return not g_clipboard_history.empty()

    def paste_choice(self, choice_index):
        if choice_index == -1:
            return
        # use normal paste command
        text = g_clipboard_history.get()[choice_index][1]
        # rotate to top
        g_clipboard_history.push_text(text)
        sublime.set_clipboard(text)
        self.view.run_command("paste")
