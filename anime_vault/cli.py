from __future__ import annotations

import argparse

from .config import DB_PATH
from .repository import ensure_database
from .server import create_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="番剧观看管理网页")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="监听地址，默认 0.0.0.0（允许局域网设备访问）",
    )
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="只初始化数据库，不启动 Web 服务",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_database()
    if args.init_db:
        print(f"Database ready: {DB_PATH}")
        return

    server = create_server(args.host, args.port)
    print(f"Serving on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
