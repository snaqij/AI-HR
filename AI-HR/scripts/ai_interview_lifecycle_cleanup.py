"""AI 面试生命周期清理任务脚本。"""

from __future__ import annotations

import argparse
import json

from ai_hr.db.session import SessionLocal
from ai_hr.services.ai_lifecycle import AIInterviewLifecycleService


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 面试生命周期清理")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不落库")
    parser.add_argument("--batch-size", type=int, default=500, help="单次处理上限")
    args = parser.parse_args()

    with SessionLocal() as session:
        service = AIInterviewLifecycleService(session)
        result = service.run_cleanup(dry_run=bool(args.dry_run), batch_size=args.batch_size)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
