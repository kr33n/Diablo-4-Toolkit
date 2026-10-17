import threading
import time
import win32gui
import win32api
import win32con

class AutoKeyService:
    def __init__(self):
        self.is_active = False
        self.running = True
        self.target_window_title = "Diablo IV"
        self.keys_to_spam = []
        self.thread = threading.Thread(target=self._spam_loop, daemon=True)
        self.thread.start()

    def set_keys(self, keys):
        self.keys_to_spam = [k.upper() for k in keys if k.strip()]

    def toggle(self):
        if self.keys_to_spam:
            self.is_active = not self.is_active
            if not self.is_active:
                self.release_all_keys()
        return self.is_active

    def get_vk_code(self, char):
        return ord(char)

    def release_all_keys(self):
        hwnd = win32gui.FindWindow(None, self.target_window_title)
        if hwnd:
            for key in self.keys_to_spam:
                vk = self.get_vk_code(key)
                win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)

    def _spam_loop(self):
        while self.running:
            if self.is_active and self.keys_to_spam:
                hwnd = win32gui.FindWindow(None, self.target_window_title)
                if hwnd:
                    for key in self.keys_to_spam:
                        vk = self.get_vk_code(key)
                        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
                else:
                    self.is_active = False # Desativa se perder a janela
            time.sleep(0.05)

    def stop(self):
        self.running = False
        self.release_all_keys()