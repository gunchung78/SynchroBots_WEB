# app/hardware/modbus_monitor.py
import serial, time, math, threading, sys, os
from typing import Callable, Dict, List, Optional

class ModbusMonitor:
    """
    RS-485 / Modbus RTU (Read Coils 0x01) 다중 코일 감시용 모니터.
    - 연속 주소구간을 한 번에 읽고, 각 코일(Mxxxx)별로 상승엣지(OFF->ON) 콜백 호출
    - 포트는 시작 시 1회 오픈 유지, 에러 시 닫고 재연결
    """
    def __init__(
        self,
        port,
        baudrate: int = 115200,
        parity: str = "N",
        stopbits: int = 1,
        bytesize: int = 8,
        timeout: float = 0.05,
        slave_id: int = 3,
        watch_addrs: Optional[List[int]] = None,  # 예: [0x0000, 0x0001, 0x0005]
        interval: float = 0.01                    # 폴링 간격(초)
    ):
        self.port = port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.timeout = timeout

        self.slave_id = slave_id
        self.watch_addrs = sorted(watch_addrs or [0x0000, 0x0001])
        self.interval = interval

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._ser: Optional[serial.Serial] = None

        # 연속 구간 계산
        self._start = min(self.watch_addrs)
        self._end   = max(self.watch_addrs)
        self._qty   = self._end - self._start + 1

        # 이전 상태 / 트리거 레디 (코일별)
        self._prev: Dict[int, Optional[bool]] = {a: None for a in self.watch_addrs}
        self._ready: Dict[int, bool] = {a: True for a in self.watch_addrs}

    # ---- CRC16(Modbus RTU) : Low byte 먼저, High byte 다음
    @staticmethod
    def _crc16(data: bytes) -> int:
        crc = 0xFFFF
        for pos in data:
            crc ^= pos
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF

    def _open_once(self) -> bool:
        if self._ser and self._ser.is_open:
            return True
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                stopbits=self.stopbits,
                bytesize=self.bytesize,
                timeout=self.timeout,
                write_timeout=2
            )
            print(f"[ModbusMonitor] Opened {self.port} (pid={os.getpid()})")
            return True
        except Exception as e:
            print(f"[ModbusMonitor] open error on {self.port}: {e}", file=sys.stderr)
            self._ser = None
            return False

    def _close(self):
        try:
            if self._ser:
                self._ser.close()
                print(f"[ModbusMonitor] Closed {self.port}")
        except Exception:
            pass
        self._ser = None

    def _read_coils_batch(self) -> Optional[List[bool]]:
        """
        Read Coils (0x01) : start=self._start, quantity=self._qty
        반환: 길이 qty 의 bool 리스트 (LSB부터 시작)
        """
        if not self._ser:
            return None

        # 요청 패킷
        pkt = bytearray([
            self.slave_id, 0x01,
            (self._start >> 8) & 0xFF, self._start & 0xFF,
            (self._qty   >> 8) & 0xFF, self._qty   & 0xFF
        ])
        c = self._crc16(pkt)
        pkt += bytes([c & 0xFF, (c >> 8) & 0xFF])  # low, high

        try:
            self._ser.write(pkt)
            time.sleep(0.005)

            data_bytes_needed = math.ceil(self._qty / 8)
            # slave, func, byte_count, data..., crc_lo, crc_hi
            resp = self._ser.read(3 + data_bytes_needed + 2)
            if len(resp) < 3 + data_bytes_needed + 2:
                return None

            # (선택) CRC 검증
            body = resp[:-2]
            r_crc = resp[-2] | (resp[-1] << 8)
            if self._crc16(body) != r_crc:
                return None

            if resp[1] != 0x01:
                return None

            byte_count = resp[2]
            data = resp[3:3+byte_count]

            bits: List[bool] = []
            for b in data:
                for bit in range(8):
                    bits.append(bool((b >> bit) & 0x01))
                    if len(bits) >= self._qty:
                        break
            return bits

        except serial.SerialTimeoutException:
            return None
        except Exception:
            return None

    def _loop(self, on_rising: Callable[[int], None]):
        print("[ModbusMonitor] started")
        backoff = 0.5
        while not self._stop.is_set():
            try:
                if not self._open_once():
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, 5.0)
                    continue
                backoff = 0.5

                with self._lock:
                    bits = self._read_coils_batch()

                if bits is not None:
                    # 코일별 현재 상태
                    for a in self.watch_addrs:
                        state = bits[a - self._start]  # 인덱스 매핑

                        if self._prev[a] is None:
                            self._prev[a] = state
                            continue

                        # OFF -> ON (상승엣지)
                        if (not self._prev[a]) and state and self._ready[a]:
                            try:
                                on_rising(a)  # 코일 주소 전달 (예: 0x0000, 0x0001)
                            except Exception as e:
                                print("callback error:", e, file=sys.stderr)
                            self._ready[a] = False

                        # ON -> OFF 되면 다음 트리거 준비
                        if self._prev[a] and (not state):
                            self._ready[a] = True

                        self._prev[a] = state

                time.sleep(self.interval)

            except Exception as e:
                print("[ModbusMonitor] monitor error:", e, file=sys.stderr)
                self._close()
                time.sleep(0.5)

        self._close()
        print("[ModbusMonitor] stopped")

    def start(self, on_rising: Callable[[int], None]):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(on_rising,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
