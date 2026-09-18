#!/usr/bin/env python3
"""
TWAMP Reflector (Session-Reflector) Skeleton.
Implements UDP reflector that echoes TWAMP-Test packets with reflector timestamp.
For production: add packet validation, rate limiting, and statistics.
"""

import socket
import struct
import time
from typing import Tuple
import logging


class TWAMPReflector:
    """TWAMP-Test reflector (RFC 5357 §4.2)."""
    
    def __init__(self, listen_addr: str, listen_port: int):
        self.listen_addr = listen_addr
        self.listen_port = listen_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((listen_addr, listen_port))
        self.packet_count = 0
        self.error_count = 0
        
        logging.basicConfig(level=logging.INFO)
        self.log = logging.getLogger('TWAMPReflector')
        
    def run(self, timeout_sec: float = None) -> None:
        """Run reflector loop: receive, echo, repeat."""
        self.sock.settimeout(timeout_sec)
        self.log.info(f"TWAMP Reflector listening on {self.listen_addr}:{self.listen_port}")
        
        while True:
            try:
                data, addr = self.sock.recvfrom(1024)
                self.packet_count += 1
                
                # Parse sender's test packet
                response = self._reflect_packet(data, addr)
                if response:
                    self.sock.sendto(response, addr)
                    
            except socket.timeout:
                if timeout_sec:
                    break
            except Exception as e:
                self.error_count += 1
                self.log.error(f"Error: {e}")
    
    def _reflect_packet(self, data: bytes, addr: Tuple[str, int]) -> bytes:
        """Echo test packet with reflector timestamp."""
        if len(data) < 16:
            self.log.warning(f"Packet too short ({len(data)} bytes) from {addr}")
            return None
        
        # Parse sender's packet: Sequence (4B) + Sender Timestamp (8B NTP) + padding
        try:
            seq, = struct.unpack('!I', data[0:4])
            sender_ts_ntp = data[4:12]  # NTP 64-bit (don't parse, just copy)
            
        except struct.error as e:
            self.log.error(f"Parse error: {e}")
            return None
        
        # Generate reflector timestamp (current time in NTP 64-bit)
        reflector_ts_ntp = self._now_ntp64()
        
        # Build response: Sequence (copied) + Sender TS (copied) + Reflector TS + Error Estimate
        # TWAMP-Test response format (§4.2.1):
        # - Sequence (4B, copied from sender)
        # - MBZ (4B)
        # - Sender Timestamp (8B NTP, copied)
        # - Reflector Timestamp (8B NTP, generated)
        # - Send Error Estimate (4B) or HMAC (authenticated)
        # - Padding to match sender packet size
        
        response = struct.pack(
            '!II8s8sI',
            seq,                    # Sequence
            0,                      # MBZ
            sender_ts_ntp,          # Sender Timestamp (echo)
            reflector_ts_ntp,       # Reflector Timestamp (generated now)
            0                       # Error Estimate (simplified; use 0)
        )
        
        # Pad to match sender's packet length
        if len(response) < len(data):
            response += b'\x00' * (len(data) - len(response))
        
        self.log.debug(f"Reflected seq={seq} from {addr} (RTT est: {time.time():.6f})")
        return response[:len(data)]  # Trim to sender's size
    
    def _now_ntp64(self) -> bytes:
        """Current time in NTP 64-bit format."""
        NTP_EPOCH_OFFSET = 2208988800  # Seconds between 1900-01-01 and 1970-01-01
        unix_now = time.time()
        ntp_sec = int(unix_now) + NTP_EPOCH_OFFSET
        ntp_frac = int((unix_now % 1) * (2 ** 32))
        return struct.pack('!II', ntp_sec, ntp_frac)
    
    def get_stats(self) -> dict:
        """Return reflector statistics."""
        return {
            'packets_reflected': self.packet_count,
            'errors': self.error_count,
            'success_rate': (self.packet_count - self.error_count) / max(self.packet_count, 1)
        }


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='TWAMP Reflector')
    parser.add_argument('--addr', default='0.0.0.0', help='Listen address')
    parser.add_argument('--port', type=int, default=862, help='Listen port')
    parser.add_argument('--timeout', type=float, help='Run timeout (seconds)')
    
    args = parser.parse_args()
    
    reflector = TWAMPReflector(args.addr, args.port)
    try:
        reflector.run(args.timeout)
    except KeyboardInterrupt:
        print(f"\n[TWAMP] Reflector stopped. Stats: {reflector.get_stats()}")
