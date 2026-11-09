#!/usr/bin/env python3
"""PC 端 viewer: 监听端口, 接收板子推来的 JPEG 帧并显示。
用法: python viewer_pc.py [PORT]
"""
import sys, socket, struct
import cv2
import numpy as np

port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", port))
srv.listen(1)
print(f"listening on :{port}, waiting for board...", flush=True)
conn, addr = srv.accept()
print("board connected:", addr, flush=True)
buf = b""
try:
    while True:
        while len(buf) < 4:
            data = conn.recv(65536)
            if not data:
                raise ConnectionResetError
            buf += data
        (size,) = struct.unpack("<I", buf[:4])
        buf = buf[4:]
        while len(buf) < size:
            data = conn.recv(65536)
            if not data:
                raise ConnectionResetError
            buf += data
        frame = cv2.imdecode(np.frombuffer(buf[:size], np.uint8), cv2.IMREAD_COLOR)
        buf = buf[size:]
        if frame is None:
            continue
        cv2.imshow("board gesture stream", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
except (ConnectionResetError, KeyboardInterrupt):
    pass
finally:
    conn.close(); srv.close(); cv2.destroyAllWindows()
    print("viewer closed", flush=True)
