from __future__ import annotations

import ctypes
import os
import struct
import threading
from dataclasses import dataclass
from typing import Callable, Iterable

import psutil


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_NOACCESS = 0x01
PAGE_READWRITE = 0x04
PAGE_GUARD = 0x100
PAGE_EXECUTE_READWRITE = 0x40
CHUNK_SIZE = 2 * 1024 * 1024
LARGE_PATCH_REGION_MIN_SIZE = 700 * 1024 * 1024
CAMERA_REGION_MIN_SIZE = 1 * 1024 * 1024
CAMERA_REGION_MAX_SIZE = 32 * 1024 * 1024

OFFSETS = {
    "FOV": 0x08,
    "Zoom": 0x24,
    "Height": 0x14,
    "Angle": 0x20,
    "Fog": 0x6C,
}

DEFAULT_PATCH_PATTERN = bytes.fromhex("DF D8 10 00 FF FF FF FF")
DEFAULT_CAMERA_PATTERN = bytes.fromhex("DF 1B 15 00 0A 00 00 00 AA")
DEFAULT_PATCH_BYTES = bytes.fromhex("DF 1B 15 00")


class CameraPatcherError(RuntimeError):
    """An error attaching to or modifying the Diablo IV process."""


class ScanCancelled(CameraPatcherError):
    """Raised when a running memory scan is cancelled."""


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.c_uint32),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.c_uint32),
        ("Protect", ctypes.c_uint32),
        ("Type", ctypes.c_uint32),
    ]


@dataclass(frozen=True)
class MemoryRegion:
    base: int
    size: int
    state: int
    protect: int
    kind: int


@dataclass
class ScanResult:
    matches_found: int = 0
    patches_written: int = 0
    first_address: int | None = None


def parse_hex_bytes(text: str, *, exact_length: int | None = None) -> bytes:
    """Parse whitespace-delimited hexadecimal bytes with a useful validation error."""
    try:
        parts = text.split()
        if not parts or any(len(part) != 2 for part in parts):
            raise ValueError
        result = bytes(int(part, 16) for part in parts)
    except ValueError as error:
        raise ValueError("Use whitespace-delimited two-digit hex bytes, e.g. '00 00 80 3F'.") from error
    if exact_length is not None and len(result) != exact_length:
        raise ValueError(f"Expected exactly {exact_length} bytes, got {len(result)}.")
    return result


def find_matches(buffer: bytes, pattern: bytes, *, start: int = 0) -> Iterable[int]:
    """Yield non-overlapping match offsets, matching the original scanner behavior."""
    if not pattern:
        raise ValueError("The scan pattern cannot be empty.")
    cursor = start
    while True:
        offset = buffer.find(pattern, cursor)
        if offset < 0:
            return
        yield offset
        cursor = offset + len(pattern)


class _WindowsMemory:
    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Diablo IV process memory access is supported only on Windows.")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        self.kernel32.OpenProcess.restype = ctypes.c_void_p
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel32.CloseHandle.restype = ctypes.c_int
        self.kernel32.VirtualQueryEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(MEMORY_BASIC_INFORMATION),
            ctypes.c_size_t,
        ]
        self.kernel32.VirtualQueryEx.restype = ctypes.c_size_t
        self.kernel32.ReadProcessMemory.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.kernel32.ReadProcessMemory.restype = ctypes.c_int
        self.kernel32.WriteProcessMemory.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.kernel32.WriteProcessMemory.restype = ctypes.c_int
        self.kernel32.VirtualProtectEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self.kernel32.VirtualProtectEx.restype = ctypes.c_int
        self.last_error = 0

    def open_process(self, process_id: int) -> int:
        rights = (
            PROCESS_QUERY_INFORMATION
            | PROCESS_VM_OPERATION
            | PROCESS_VM_READ
            | PROCESS_VM_WRITE
        )
        handle = self.kernel32.OpenProcess(rights, False, process_id)
        if not handle:
            error = ctypes.get_last_error()
            raise CameraPatcherError(
                f"OpenProcess failed for PID {process_id}. Win32 error: {error}. "
                "Try running as Administrator."
            )
        return int(handle)

    def close_process(self, handle: int) -> None:
        if handle and not self.kernel32.CloseHandle(handle):
            error = ctypes.get_last_error()
            raise CameraPatcherError(f"CloseHandle failed. Win32 error: {error}.")

    def query(self, handle: int, address: int) -> MemoryRegion | None:
        info = MEMORY_BASIC_INFORMATION()
        result = self.kernel32.VirtualQueryEx(
            handle, ctypes.c_void_p(address), ctypes.byref(info), ctypes.sizeof(info)
        )
        if not result:
            return None
        return MemoryRegion(
            base=int(info.BaseAddress or 0),
            size=int(info.RegionSize),
            state=int(info.State),
            protect=int(info.Protect),
            kind=int(info.Type),
        )

    def read(self, handle: int, address: int, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t()
        ok = self.kernel32.ReadProcessMemory(
            handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(bytes_read),
        )
        if not ok and bytes_read.value == 0:
            return b""
        return buffer.raw[: bytes_read.value]

    def write(self, handle: int, address: int, data: bytes) -> bool:
        if not data:
            return True
        target = ctypes.c_void_p(address)
        size = len(data)
        old_protect = ctypes.c_uint32()
        self.kernel32.VirtualProtectEx(
            handle, target, size, PAGE_EXECUTE_READWRITE, ctypes.byref(old_protect)
        )
        buffer = ctypes.create_string_buffer(data)
        bytes_written = ctypes.c_size_t()
        try:
            ok = self.kernel32.WriteProcessMemory(
                handle,
                target,
                buffer,
                size,
                ctypes.byref(bytes_written),
            )
            self.last_error = 0 if ok and bytes_written.value == size else ctypes.get_last_error()
        finally:
            if old_protect.value:
                restored_protect = ctypes.c_uint32()
                self.kernel32.VirtualProtectEx(
                    handle, target, size, old_protect.value, ctypes.byref(restored_protect)
                )
        return bool(ok and bytes_written.value == size)


class CameraPatcherService:
    """Scans Diablo IV memory, applies its camera patch and writes camera values."""

    offsets = OFFSETS
    reset_values = {
        "FOV": 0.6108652353,
        "Zoom": 1.350000024,
        "Height": -0.200000003,
        "Angle": 18.2003994,
        "Fog": 1.0,
    }

    def __init__(
        self,
        process_name: str = "Diablo IV",
        process_id: int | None = None,
        pattern: bytes = DEFAULT_PATCH_PATTERN,
        second_pattern: bytes = DEFAULT_CAMERA_PATTERN,
        new_bytes: bytes = DEFAULT_PATCH_BYTES,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        if len(new_bytes) != 4:
            raise ValueError("Replacement must be exactly 4 bytes.")
        if not pattern or not second_pattern:
            raise ValueError("Scan patterns cannot be empty.")
        self.process_name = process_name
        self.process_id = process_id
        self.pattern = pattern
        self.second_pattern = second_pattern
        self.new_bytes = new_bytes
        self.progress_callback = progress_callback
        self.is_attached = False
        self.attached_process_id: int | None = None
        self.patch_address: int | None = None
        self.camera_address: int | None = None
        self._memory: _WindowsMemory | None = None
        self._handle = 0
        self._scan_cancel = threading.Event()
        self._writer_stop = threading.Event()
        self._writer_thread: threading.Thread | None = None
        self._writer_error: CameraPatcherError | None = None
        self.last_patch_result = ScanResult()
        self.last_camera_result = ScanResult()
        self.patch_scan_path = ""
        self.camera_scan_path = ""

    def _progress(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)

    def find_process_ids(self) -> list[int]:
        if self.process_id is not None:
            try:
                process = psutil.Process(self.process_id)
                if not process.is_running():
                    return []
                return [self.process_id]
            except psutil.Error:
                return []
        expected = self.process_name.casefold()
        matches: list[int] = []
        for process in psutil.process_iter(["pid", "name"]):
            try:
                name = process.info["name"] or ""
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            if name.casefold().removesuffix(".exe") == expected.casefold().removesuffix(".exe"):
                matches.append(int(process.info["pid"]))
        return matches

    def attach(self) -> bool:
        """Return whether at least one matching process is running."""
        return bool(self.find_process_ids())

    def cancel_scan(self) -> None:
        self._scan_cancel.set()

    def _check_cancelled(self) -> None:
        if self._scan_cancel.is_set():
            raise ScanCancelled("Scan cancelled.")

    @staticmethod
    def _is_private_read_write(region: MemoryRegion) -> bool:
        return (
            region.state == MEM_COMMIT
            and region.kind == MEM_PRIVATE
            and region.protect == PAGE_READWRITE
        )

    @staticmethod
    def _is_readable(region: MemoryRegion) -> bool:
        return (
            region.state == MEM_COMMIT
            and (region.protect & (PAGE_NOACCESS | PAGE_GUARD)) == 0
        )

    def _collect_regions(
        self,
        *,
        private_read_write_only: bool,
        minimum_size: int = 0,
        maximum_size: int = 0,
    ) -> list[MemoryRegion]:
        assert self._memory is not None
        regions: list[MemoryRegion] = []
        address = 0
        while True:
            self._check_cancelled()
            region = self._memory.query(self._handle, address)
            if region is None:
                break
            if region.size <= 0:
                break
            next_address = region.base + region.size
            size_ok = region.size >= minimum_size and (
                maximum_size == 0 or region.size <= maximum_size
            )
            eligible = (
                self._is_private_read_write(region)
                if private_read_write_only
                else self._is_readable(region)
            )
            if eligible and size_ok:
                regions.append(region)
            if next_address <= address or next_address <= region.base:
                break
            address = next_address
        return regions

    def _scan_regions(
        self,
        regions: Iterable[MemoryRegion],
        pattern: bytes,
        *,
        replacement: bytes | None = None,
        stop_after_first: bool = False,
    ) -> ScanResult:
        assert self._memory is not None
        result = ScanResult()
        overlap_length = len(pattern) - 1
        for region in regions:
            position = 0
            overlap = b""
            while position < region.size:
                self._check_cancelled()
                chunk_size = min(CHUNK_SIZE, region.size - position)
                read_address = region.base + position
                current = self._memory.read(self._handle, read_address, chunk_size)
                if current:
                    combined = overlap + current
                    prefix_length = len(overlap)
                    for offset in find_matches(combined, pattern):
                        match_address = read_address - prefix_length + offset
                        if match_address < region.base or match_address + len(pattern) <= read_address:
                            continue
                        result.matches_found += 1
                        if result.first_address is None or match_address < result.first_address:
                            result.first_address = match_address
                        if replacement is not None:
                            if not self._memory.write(self._handle, match_address, replacement):
                                error = ctypes.get_last_error()
                                if self._memory.last_error:
                                    error = self._memory.last_error
                                raise CameraPatcherError(
                                    f"WriteProcessMemory failed at 0x{match_address:X}. "
                                    f"Win32 error: {error}."
                                )
                            result.patches_written += 1
                        if stop_after_first:
                            return result
                    overlap = combined[-overlap_length:] if overlap_length else b""
                else:
                    overlap = b""
                position += chunk_size
        return result

    def _scan_with_fallback(
        self,
        pattern: bytes,
        *,
        stop_after_first: bool,
        replacement: bytes | None = None,
        camera_targeted: bool = False,
    ) -> tuple[ScanResult, str]:
        if camera_targeted:
            passes = [
                (True, CAMERA_REGION_MIN_SIZE, CAMERA_REGION_MAX_SIZE, "targeted"),
                (True, 0, 0, "all private RW"),
                (False, 0, 0, "fallback"),
            ]
        else:
            passes = [
                (True, LARGE_PATCH_REGION_MIN_SIZE, 0, "targeted"),
                (True, 0, 0, "all private RW"),
                (False, 0, 0, "fallback"),
            ]
        last_result = ScanResult()
        last_path = passes[-1][3]
        for private_only, minimum, maximum, path in passes:
            self._check_cancelled()
            regions = self._collect_regions(
                private_read_write_only=private_only,
                minimum_size=minimum,
                maximum_size=maximum,
            )
            last_result = self._scan_regions(
                regions,
                pattern,
                replacement=replacement,
                stop_after_first=stop_after_first,
            )
            last_path = path
            if last_result.matches_found:
                break
        return last_result, last_path

    def scan_and_patch(
        self, *, patch_all: bool = False, require_patch: bool = True
    ) -> bool:
        """Attach, locate the patch and camera structure, and retain the process handle."""
        if self._handle:
            self.close()
        self._scan_cancel.clear()
        self.last_patch_result = ScanResult()
        self.last_camera_result = ScanResult()
        self.patch_scan_path = ""
        self.camera_scan_path = ""
        pids = self.find_process_ids()
        if not pids:
            raise CameraPatcherError(f"Could not find process '{self.process_name}'.")
        if len(pids) > 1:
            raise CameraPatcherError(
                f"Found multiple '{self.process_name}' processes. "
                f"Use --process-id to select one of: {', '.join(map(str, pids))}."
            )
        pid = pids[0]
        self._memory = _WindowsMemory()
        self._handle = self._memory.open_process(pid)
        self.attached_process_id = pid
        try:
            self._progress(f"Finding patch location in PID {pid}...")
            patch_result, patch_path = self._scan_with_fallback(
                self.pattern,
                stop_after_first=not patch_all,
                replacement=self.new_bytes,
            )
            self.last_patch_result = patch_result
            self.patch_scan_path = patch_path
            self.patch_address = patch_result.first_address
            if not patch_result.patches_written and require_patch:
                raise CameraPatcherError(
                    f"Patch pattern was not found or could not be patched: "
                    f"{self.pattern.hex(' ').upper()}"
                )
            if patch_result.patches_written:
                self._progress(
                    f"Patch found by {patch_path} scan; locating camera values..."
                )
            else:
                self._progress("Patch pattern not found; locating camera values...")
            camera_result, camera_path = self._scan_with_fallback(
                self.second_pattern,
                stop_after_first=True,
                camera_targeted=True,
            )
            self.last_camera_result = camera_result
            self.camera_scan_path = camera_path
            if camera_result.first_address is None:
                raise CameraPatcherError(
                    f"Camera values pattern was not found: "
                    f"{self.second_pattern.hex(' ').upper()}"
                )
            self.camera_address = camera_result.first_address
            self.is_attached = True
            self._progress(
                f"Ready. Patch: {patch_path}; camera values: {camera_path}."
            )
            return True
        except Exception:
            self.close()
            raise

    def read_camera_value(self, name: str) -> float:
        if name not in self.offsets:
            raise KeyError(f"Unknown camera value: {name}")
        if not self.is_attached or self.camera_address is None or self._memory is None:
            raise CameraPatcherError("Scan before reading camera values.")
        data = self._memory.read(
            self._handle, self.camera_address + self.offsets[name], 4
        )
        if len(data) != 4:
            raise CameraPatcherError(f"Could not read the {name} camera value.")
        return struct.unpack("<f", data)[0]

    def write_camera_value(self, name: str, value: float) -> bool:
        if name not in self.offsets:
            raise KeyError(f"Unknown camera value: {name}")
        if not self.is_attached or self.camera_address is None or self._memory is None:
            raise CameraPatcherError("Scan before writing camera values.")
        data = struct.pack("<f", float(value))
        address = self.camera_address + self.offsets[name]
        if not self._memory.write(self._handle, address, data):
            error = self._memory.last_error or ctypes.get_last_error()
            raise CameraPatcherError(
                f"Could not write the {name} camera value at 0x{address:X}. "
                f"Win32 error: {error}."
            )
        return True

    def apply_values(self, values: dict[str, float]) -> None:
        for name, value in values.items():
            if name in self.offsets:
                self.write_camera_value(name, value)

    def start_loop_writer(self) -> None:
        if not self.is_attached or self.patch_address is None or self._memory is None:
            raise CameraPatcherError("Scan before starting the patch writer.")
        if self._writer_thread is not None and self._writer_thread.is_alive():
            return
        self._writer_stop.clear()
        self._writer_error = None

        def write_loop() -> None:
            while not self._writer_stop.is_set():
                if self._memory is not None and self._handle and self.patch_address is not None:
                    try:
                        if not self._memory.write(self._handle, self.patch_address, self.new_bytes):
                            error = ctypes.get_last_error()
                            raise CameraPatcherError(
                                f"Patch writer failed at 0x{self.patch_address:X}. "
                                f"Win32 error: {error}."
                            )
                    except CameraPatcherError as error:
                        self._writer_error = error
                        self._writer_stop.set()
                        return
                self._writer_stop.wait(0.001)

        self._writer_thread = threading.Thread(
            target=write_loop, name="DiabloCameraPatchWriter", daemon=True
        )
        self._writer_thread.start()

    def stop_loop_writer(self) -> None:
        self._writer_stop.set()
        if self._writer_thread is not None and self._writer_thread is not threading.current_thread():
            self._writer_thread.join()
        self._writer_thread = None
        self.close()

    def close(self) -> None:
        self.stop_writer_only()
        if self._handle and self._memory is not None:
            handle, self._handle = self._handle, 0
            self._memory.close_process(handle)
        self._memory = None
        self.is_attached = False
        self.attached_process_id = None
        self.patch_address = None
        self.camera_address = None

    def stop_writer_only(self) -> None:
        self._writer_stop.set()
        thread = self._writer_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join()
        self._writer_thread = None

    @property
    def writer_error(self) -> CameraPatcherError | None:
        return self._writer_error

    @property
    def writer_running(self) -> bool:
        return self._writer_thread is not None and self._writer_thread.is_alive()
