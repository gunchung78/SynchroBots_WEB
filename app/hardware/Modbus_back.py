# app/hardware/Modbus.py
import serial, time, threading, sys

class ModbusMonitor:
    def __init__(self, port='COM3', baudrate=115200, slave_id=3, coil_addr=0x0000, interval=0.01):
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.coil_addr = coil_addr
        self.interval = interval
        self.ser = None
        self._stop = threading.Event()
        self._thread = None
        self._prev_state = None
        self._trigger_ready = True  # OFF→ON만 1회 트리거

    # ---- CRC16(Modbus RTU)
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

    def _open(self):
        if self.ser and self.ser.is_open:
            return
        self.ser = serial.Serial(
            port=self.port, baudrate=self.baudrate, bytesize=8,
            parity='N', stopbits=1, timeout=0.05, write_timeout=2
        )

    def _close(self):
        try:
            if self.ser:
                self.ser.close()
        except:
            pass
        self.ser = None

    def _read_coil_once(self):
        # Function 0x01: Read Coils, 1개 읽기
        pkt = bytearray([
            self.slave_id, 0x01,
            (self.coil_addr >> 8) & 0xFF, self.coil_addr & 0xFF,
            0x00, 0x01
        ])
        crc = self._crc16(pkt)
        pkt.append(crc & 0xFF)           # low
        pkt.append((crc >> 8) & 0xFF)    # high

        try:
            self.ser.write(pkt)
            time.sleep(0.005)
            resp = self.ser.read(7)  # slave, func, bytecount, data, CRC(2)
            if len(resp) < 5:
                return None
            data_byte = resp[3]
            return bool(data_byte & 0x01)
        except serial.SerialTimeoutException:
            return None
        except Exception:
            return None

    def _loop(self, on_rising):
        print("📡 Modbus monitor started")
        while not self._stop.is_set():
            try:
                self._open()
                state = self._read_coil_once()
                if state is not None:
                    if self._prev_state is None:
                        self._prev_state = state

                    # OFF -> ON (상승엣지)
                    if not self._prev_state and state and self._trigger_ready:
                        try:
                            on_rising()  # 콜백 호출
                        except Exception as e:
                            print("callback error:", e, file=sys.stderr)
                        self._trigger_ready = False

                    # ON -> OFF (다음 트리거 준비)
                    if self._prev_state and not state:
                        self._trigger_ready = True

                    self._prev_state = state

                time.sleep(self.interval)
            except Exception as e:
                print("monitor error:", e, file=sys.stderr)
                self._close()
                time.sleep(0.5)
        self._close()
        print("🛑 Modbus monitor stopped")

    def start(self, on_rising):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(on_rising,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
