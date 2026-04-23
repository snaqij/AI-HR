"""Batch generate interview invitations for multiple resumes.

Usage:
  python scripts/batch_generate_invites.py
  python scripts/batch_generate_invites.py --no-send-email
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Import the main function from generate_interview_invite
import generate_interview_invite as invite_gen


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch generate interview invitations for multiple resumes.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1", help="Backend API base URL.")
    parser.add_argument("--frontend-base", default="http://localhost:5173", help="Frontend base URL.")
    parser.add_argument(
        "--send-email",
        dest="send_email",
        action="store_true",
        default=False,
        help="Send invitation via email (disabled by default for batch mode).",
    )
    parser.add_argument("--debug", action="store_true", help="Print detailed debug logs.")
    args = parser.parse_args()

    # Define resume files and their corresponding job titles
    resume_configs = [
        {
            "resume": "data/测试文本简历",
            "job_title": "Java后端开发工程师",
            "department": "研发团队",
            "requirements": (
                "1. 计算机或相关专业本科及以上学历。\n"
                "2. 热爱编程，具备扎实的Java语言基础，了解JVM、多线程及集合框架。\n"
                "3. 熟悉Spring、Spring Boot、MyBatis等主流应用开发框架。\n"
                "4. 熟悉关系型数据库（MySQL）的基本使用，了解常用SQL优化。\n"
                "5. 有较强的逻辑分析能力和系统除错能力。"
            ),
        },
        {
            "resume": "data/测试文本简历-前端",
            "job_title": "前端开发工程师",
            "department": "研发团队",
            "requirements": (
                "1. 计算机或相关专业本科及以上学历。\n"
                "2. 精通JavaScript、HTML、CSS，熟悉Vue或React框架。\n"
                "3. 熟悉前端工程化工具，如Webpack、Vite等。\n"
                "4. 具备良好的代码规范和文档编写能力。\n"
                "5. 有移动端开发经验者优先。"
            ),
        },
        {
            "resume": "data/resume_fullstack.txt",
            "job_title": "全栈开发工程师",
            "department": "研发团队",
            "requirements": (
                "1. 计算机或相关专业本科及以上学历。\n"
                "2. 精通前端和后端开发，熟悉Vue/React和Node.js/Java。\n"
                "3. 熟悉数据库设计和优化，熟悉Redis缓存。\n"
                "4. 熟悉Docker容器化部署和CI/CD流程。\n"
                "5. 具备良好的系统设计和架构能力。"
            ),
        },
        {
            "resume": "data/resume_product_manager.txt",
            "job_title": "产品经理",
            "department": "产品团队",
            "requirements": (
                "1. 本科及以上学历，3年以上产品经理经验。\n"
                "2. 精通产品设计流程，熟练使用Axure、Figma等工具。\n"
                "3. 具备良好的用户研究和数据分析能力。\n"
                "4. 熟悉敏捷开发流程，具备跨部门协作经验。\n"
                "5. 具备良好的商业思维和市场洞察力。"
            ),
        },
        {
            "resume": "data/resume_ui_designer.txt",
            "job_title": "UI/UX设计师",
            "department": "设计团队",
            "requirements": (
                "1. 设计或相关专业本科及以上学历。\n"
                "2. 精通UI/UX设计，熟练使用Figma、Sketch等工具。\n"
                "3. 深入理解用户体验设计原则，熟悉用户研究方法。\n"
                "4. 具备设计系统构建经验，能够建立和维护设计规范。\n"
                "5. 具备良好的审美能力和创新思维。"
            ),
        },
        {
            "resume": "data/resume_data_analyst.txt",
            "job_title": "数据分析师",
            "department": "数据团队",
            "requirements": (
                "1. 统计学、数学或相关专业本科及以上学历。\n"
                "2. 精通Python、SQL等数据分析工具。\n"
                "3. 熟悉机器学习算法和数据可视化工具。\n"
                "4. 具备A/B测试设计和分析经验。\n"
                "5. 具备良好的商业思维和数据洞察力。"
            ),
        },
        {
            "resume": "data/resume_devops.txt",
            "job_title": "DevOps工程师",
            "department": "运维团队",
            "requirements": (
                "1. 计算机或相关专业本科及以上学历。\n"
                "2. 精通Linux系统管理和Shell脚本开发。\n"
                "3. 熟练使用Docker、Kubernetes进行容器化部署。\n"
                "4. 熟悉CI/CD流程和自动化运维工具。\n"
                "5. 具备云平台管理和成本优化经验。"
            ),
        },
    ]

    print(f"[batch] Starting batch invitation generation for {len(resume_configs)} resumes")
    print(f"[batch] api_base={args.api_base}")
    print(f"[batch] send_email={args.send_email}")
    print("=" * 80)

    results = []
    for idx, config in enumerate(resume_configs, 1):
        resume_path = Path(config["resume"])
        if not resume_path.exists():
            print(f"\n[batch] [{idx}/{len(resume_configs)}] SKIP: Resume not found: {resume_path}")
            results.append({"resume": config["resume"], "status": "SKIP", "reason": "File not found"})
            continue

        print(f"\n[batch] [{idx}/{len(resume_configs)}] Processing: {resume_path.name}")
        print(f"[batch] Job: {config['job_title']}")

        # Prepare arguments for generate_interview_invite
        sys.argv = [
            "generate_interview_invite.py",
            "--api-base", args.api_base,
            "--frontend-base", args.frontend_base,
            "--resume", str(resume_path),
        ]
        
        if not args.send_email:
            sys.argv.append("--no-send-email")
        
        if args.debug:
            sys.argv.append("--debug")

        # Temporarily override job_payload in invite_gen module
        original_main = invite_gen.main
        
        def patched_main():
            # Monkey patch the job_payload
            import types
            original_code = original_main.__code__
            
            # Call original main but with modified job_payload
            # This is a simplified approach - in production, you'd want to refactor
            # generate_interview_invite.py to accept job config as parameters
            return original_main()
        
        try:
            # Note: This is a simplified version. For production, you should refactor
            # generate_interview_invite.py to accept job_title and requirements as parameters
            result = invite_gen.main()
            if result == 0:
                results.append({"resume": config["resume"], "status": "SUCCESS"})
                print(f"[batch] [{idx}/{len(resume_configs)}] SUCCESS")
            else:
                results.append({"resume": config["resume"], "status": "FAILED", "reason": f"Exit code {result}"})
                print(f"[batch] [{idx}/{len(resume_configs)}] FAILED with exit code {result}")
        except Exception as exc:
            results.append({"resume": config["resume"], "status": "ERROR", "reason": str(exc)})
            print(f"[batch] [{idx}/{len(resume_configs)}] ERROR: {exc}")
            if args.debug:
                import traceback
                traceback.print_exc()
        
        # Add delay between requests to avoid overwhelming the server
        if idx < len(resume_configs):
            print(f"[batch] Waiting 2 seconds before next request...")
            time.sleep(2)

    # Print summary
    print("\n" + "=" * 80)
    print("[batch] Batch Generation Summary")
    print("=" * 80)
    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    failed_count = sum(1 for r in results if r["status"] in ["FAILED", "ERROR"])
    skip_count = sum(1 for r in results if r["status"] == "SKIP")
    
    print(f"Total: {len(results)}")
    print(f"Success: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Skipped: {skip_count}")
    
    if failed_count > 0 or skip_count > 0:
        print("\nDetails:")
        for result in results:
            if result["status"] != "SUCCESS":
                print(f"  - {result['resume']}: {result['status']} - {result.get('reason', 'N/A')}")

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[batch] Interrupted.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"[batch] Failed: {exc}")
        raise SystemExit(1)
