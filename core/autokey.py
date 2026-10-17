import threading
import win32gui
import win32api
import win32con

class AutoKeyService:
    MIN_INTERVAL_MS = 10
    MAX_INTERVAL_MS = 5000
    DEFAULT_INTERVAL_MS = 100

    def __init__(self):
        self.is_active = False
        self.running = True
        self.target_window_title = "Diablo IV"
        self.keys_to_spam = []
        self.interval_ms = self.DEFAULT_INTERVAL_MS
        self._state_lock = threading.Lock()
        self._wake_event = threading.Event()
        self.thread = threading.Thread(target=self._spam_loop, daemon=True)
        self.thread.start()

    def set_keys(self, keys):
        with self._state_lock:
            self.keys_to_spam = [k.upper() for k in keys if k.strip()]
        self._wake_event.set()

    def set_interval(self, interval_ms: int) -> None:
        if (
            isinstance(interval_ms, bool)
            or not isinstance(interval_ms, int)
            or not self.MIN_INTERVAL_MS <= interval_ms <= self.MAX_INTERVAL_MS
        ):
            raise ValueError(
                f"The interval must be between {self.MIN_INTERVAL_MS} and "
                f"{self.MAX_INTERVAL_MS} ms."
            )
        with self._state_lock:
            self.interval_ms = interval_ms
        self._wake_event.set()

    def toggle(self):
        with self._state_lock:
            if self.keys_to_spam:
                self.is_active = not self.is_active
            is_active = self.is_active
        if not is_active:
            self.release_all_keys()
        self._wake_event.set()
        return is_active

    def get_vk_code(self, char):
        return ord(char)

    def release_all_keys(self):
        with self._state_lock:
            keys = self.keys_to_spam.copy()
        hwnd = win32gui.FindWindow(None, self.target_window_title)
        if hwnd:
            for key in keys:
                vk = self.get_vk_code(key)
                win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)

    def _spam_loop(self):
        while True:
            self._wake_event.clear()
            with self._state_lock:
                is_active = self.is_active
                keys = self.keys_to_spam.copy()
                interval_ms = self.interval_ms
                running = self.running
            if not running:
                return

            if is_active and keys:
                hwnd = win32gui.FindWindow(None, self.target_window_title)
                if hwnd:
                    for key in keys:
                        with self._state_lock:
                            if not self.running or not self.is_active:
                                break
                            if key not in self.keys_to_spam:
                                continue
                            vk = self.get_vk_code(key)
                            win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
                            win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)
                else:
                    with self._state_lock:
                        self.is_active = False
                    self._wake_event.set()

            self._wake_event.wait(interval_ms / 1000)

    def stop(self):
        with self._state_lock:
            self.running = False
            self.is_active = False
        self._wake_event.set()
        self.release_all_keys()