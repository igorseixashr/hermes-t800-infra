#!/usr/bin/env python3
"""
OWAMP One-Way Latency Probe Skeleton.
Demonstrates OWAMP-Control connection setup and test session creation.
For production: add encryption, error handling, and result collection.
"""

import socket
import struct
import time
from typing import Tuple, Optional
from hashlib import sha1, sha256
import hmac


class OWAMPControl:
    """OWAMP-Control client for session negotiation (RFC 4656)."""
    
    OWAMP_CONTROL_PORT = 861
    MODE_UNAUTHENTICATED = 1
    MODE_AUTHENTICATED = 2
    MODE_ENCRYPTED = 4
    
    def __init__(self, server_addr: str, mode: int = MODE_UNAUTHENTICATED):
        self.server_addr = server_addr
        self.mode = mode
        self.sock = None
        self.shared_secret: Optional[bytes] = None
        
    def connect(self, shared_secret: Optional[str] = None) -> None:
        """Establish TCP connection and perform greeting."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.server_addr, self.OWAMP_CONTROL_PORT))
        
        if shared_secret:
            self.shared_secret = shared_secret.encode('ascii')
        
        # Receive server greeting
        greeting = self.sock.recv(64)
        self._parse_greeting(greeting)
        
    def _parse_greeting(self, data: bytes) -> None:
        """Parse server greeting (RFC 4656 §3.1)."""
        if len(data) < 64:
            raise ValueError(f"Greeting too short: {len(data)} bytes")
        
        # Unpack: 12 unused + 4 Modes + 16 Challenge + 16 Salt + 4 Count + 12 MBZ
        modes, = struct.unpack('!I', data[12:16])
        challenge = data[16:32]
        salt = data[32:48]
        count, = struct.unpack('!I', data[48:52])
        
        print(f"[OWAMP] Server modes: 0x{modes:x}, PBKDF2 count: {count}")
        
        # If authenticated: derive key from shared_secret using salt/count
        if self.mode & self.MODE_AUTHENTICATED and self.shared_secret:
            self.session_key = self._derive_key(
                self.shared_secret, salt, count
            )
    
    def _derive_key(self, secret: bytes, salt: bytes, count: int) -> bytes:
        """PBKDF2-SHA1 key derivation (RFC 4656 §3.1)."""
        key = secret
        for _ in range(count):
            key = hmac.new(salt, key, sha1).digest()
        return key[:16]  # AES-128
    
    def request_session(self, sender_addr: str, sender_port: int,
                       receiver_addr: str, receiver_port: int,
                       packet_count: int = 100,
                       packet_interval_ms: float = 100.0) -> None:
        """Send Request-Session command (RFC 4656 §3.5)."""
        # Simplified: unauthenticated mode
        cmd_packet = struct.pack(
            '!BIHHHHIIHHIIHHBBBBBBBB16s16s',
            0,  # Command Number: Request-Session
            0,  # IPVN, Conf-Sender, Conf-Receiver (MBZ for simple)
            sender_port,
            receiver_port,
            # ... Additional fields per RFC
            packet_count,
            int(packet_interval_ms * 1000),  # Interval in microseconds
            *[0] * 20  # Placeholder for remaining fields
        )
        self.sock.send(cmd_packet)
        print(f"[OWAMP] Requested session: {sender_addr}:{sender_port} → "
              f"{receiver_addr}:{receiver_port}")


class OWAMPSender:
    """OWAMP-Test sender (RFC 4656 §4.1)."""
    
    def __init__(self, local_addr: str, remote_addr: str, remote_port: int):
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.remote_port = remote_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((local_addr, 0))
        
    def send_test_packet(self, seq: int, timestamp: float) -> None:
        """Send OWAMP-Test packet with sequence and timestamp."""
        # OWAMP-Test header: 16 bytes (sequence + timestamp + HMAC placeholder)
        # Format: 4B Sequence + 4B unused + 8B Timestamp (NTP 64-bit)
        ntp_ts = self._to_ntp64(timestamp)
        packet = struct.pack('!II8s', seq, 0, ntp_ts)
        self.sock.sendto(packet, (self.remote_addr, self.remote_port))
    
    def _to_ntp64(self, unix_ts: float) -> bytes:
        """Convert Unix timestamp to NTP 64-bit format."""
        # NTP epoch: 1900-01-01; Unix epoch: 1970-01-01 (2208988800 sec diff)
        NTP_EPOCH_OFFSET = 2208988800
        ntp_sec = int(unix_ts) + NTP_EPOCH_OFFSET
        ntp_frac = int((unix_ts % 1) * (2 ** 32))
        return struct.pack('!II', ntp_sec, ntp_frac)


class OWAMPReceiver:
    """OWAMP-Test receiver (RFC 4656 §4.2)."""
    
    def __init__(self, listen_addr: str, listen_port: int):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((listen_addr, listen_port))
        self.results = []
        
    def receive_packets(self, timeout_sec: float = 60) -> list:
        """Collect test packets and log arrival times."""
        self.sock.settimeout(timeout_sec)
        start = time.time()
        
        while time.time() - start < timeout_sec:
            try:
                data, addr = self.sock.recvfrom(1024)
                arrival_ts = time.time()
                
                if len(data) >= 8:
                    seq, _ = struct.unpack('!II', data[:8])
                    sender_ts = self._from_ntp64(data[8:16])
                    one_way_delay = arrival_ts - sender_ts
                    
                    self.results.append({
                        'sequence': seq,
                        'sender_ts': sender_ts,
                        'arrival_ts': arrival_ts,
                        'one_way_delay_ms': one_way_delay * 1000,
                        'source': addr
                    })
                    
            except socket.timeout:
                break
        
        return self.results
    
    def _from_ntp64(self, data: bytes) -> float:
        """Convert NTP 64-bit timestamp to Unix time."""
        NTP_EPOCH_OFFSET = 2208988800
        ntp_sec, ntp_frac = struct.unpack('!II', data[:8])
        unix_sec = ntp_sec - NTP_EPOCH_OFFSET
        frac = ntp_frac / (2 ** 32)
        return unix_sec + frac


if __name__ == '__main__':
    # Demo: Connect, setup, measure
    ctrl = OWAMPControl('192.0.2.1', mode=OWAMPControl.MODE_UNAUTHENTICATED)
    try:
        ctrl.connect()
        ctrl.request_session('192.0.2.10', 5000, '192.0.2.1', 5001, packet_count=100)
        print("[OWAMP] Session requested. Run receiver and sender separately.")
    except Exception as e:
        print(f"[ERROR] {e}")
