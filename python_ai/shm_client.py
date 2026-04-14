from __future__ import annotations

import mmap
import struct
from dataclasses import dataclass


@dataclass
class SignalPacket:
    symbol: bytes
    price_flip_prob: float
    direction: int
    model_ts_ns: int


class MockSharedMemoryPublisher:
    """Simple mmap-based prototype; production should use boost::interprocess-compatible schema."""

    PACK_FMT = "16s f b q"

    def __init__(self, file_path: str = "bharat_alpha_signal.bin") -> None:
        self.size = struct.calcsize(self.PACK_FMT)
        self.fd = open(file_path, "w+b")
        self.fd.truncate(self.size)
        self.mm = mmap.mmap(self.fd.fileno(), self.size)

    def publish(self, signal: SignalPacket) -> None:
        payload = struct.pack(
            self.PACK_FMT,
            signal.symbol.ljust(16, b"\x00"),
            signal.price_flip_prob,
            signal.direction,
            signal.model_ts_ns,
        )
        self.mm.seek(0)
        self.mm.write(payload)
        self.mm.flush()


if __name__ == "__main__":
    pub = MockSharedMemoryPublisher()
    pub.publish(SignalPacket(b"RELIANCE", 0.73, 1, 1713075900000000000))
    print("published mock signal")
