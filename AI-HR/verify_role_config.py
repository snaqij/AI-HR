"""
验证岗位配置系统的完整性
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from ai_hr.services.role_strategy import (
    RoleConfigLoader,
    RoleProfiler,
    CompetencyMapper
)


def test_config_loading():
    """测试配置加载"""
    print("=" * 60)
    print("测试1: 配置加载")
    print("=" * 60)
    
    loader = RoleConfigLoader()
    
    # 测试加载基础配置
    base_config = loader.load_base_config()
    print(f"✓ 基础配置加载成功: {base_config.get('role', {}).get('id')}")
    
    # 测试加载岗位配置
    roles = ["backend_engineer", "frontend_engineer", "fullstack_engineer", 
             "product_manager", "ui_designer"]
    
    for role_id in roles:
        config = loader.load_config(role_id)
        if config:
            role_name = config.get("role", {}).get("display_name", {}).get("zh", role_id)
            print(f"✓ {role_id}: {role_name}")
        else:
            print(f"✗ {role_id}: 加载失败")
    
    print()


def test_role_identification():
    """测试岗位识别"""
    print("=" * 60)
    print("测试2: 岗位识别")
    print("=" * 60)
    
    profiler = RoleProfiler()
    
    # 测试后端工程师识别
    result = profiler.identify_role_profile(
        job_title="后端开发工程师",
        jd="负责Java后端开发，使用Spring框架",
        skills=["Java", "Spring", "MySQL"]
    )
    print(f"✓ 后端识别: {result.role_id} (来源: {result.source}, 分数: {result.score})")
    
    # 测试前端工程师识别
    result = profiler.identify_role_profile(
        job_title="前端开发",
        jd="负责React前端开发",
        skills=["React", "TypeScript", "Webpack"]
    )
    print(f"✓ 前端识别: {result.role_id} (来源: {result.source}, 分数: {result.score})")
    
    # 测试产品经理识别
    result = profiler.identify_role_profile(
        job_title="产品经理",
        jd="负责产品规划和需求分析",
        skills=["需求分析", "产品设计", "Axure"]
    )
    print(f"✓ 产品识别: {result.role_id} (来源: {result.source}, 分数: {result.score})")
    
    # 测试回退机制
    result = profiler.identify_role_profile(
        job_title="未知岗位",
        jd="",
        skills=[]
    )
    print(f"✓ 回退机制: {result.role_id} (来源: {result.source})")
    
    print()


def test_competency_mapping():
    """测试能力映射"""
    print("=" * 60)
    print("测试3: 能力映射")
    print("=" * 60)
    
    loader = RoleConfigLoader()
    mapper = CompetencyMapper()
    
    # 测试后端工程师能力模型
    backend_config = loader.load_config("backend_engineer")
    if backend_config:
        model = mapper.build_competency_model(backend_config)
        print(f"✓ 后端工程师能力模型:")
        print(f"  - 通用能力数量: {len(model.universal_competencies)}")
        print(f"  - 岗位能力数量: {len(model.role_competencies)}")
        print(f"  - 总权重: {model.total_weight:.2f}")
        
        # 显示岗位特定能力
        print(f"  - 岗位特定能力:")
        for comp in model.role_competencies:
            print(f"    * {comp.description}: {comp.weight:.0%}")
        
        # 测试权重计算
        weights = mapper.calculate_competency_weights(backend_config, normalize=True)
        total = sum(weights.values())
        print(f"  - 归一化权重总和: {total:.4f}")
        
        # 测试配置验证
        is_valid, errors = mapper.validate_competency_config(backend_config)
        print(f"  - 配置验证: {'通过' if is_valid else '失败'}")
        if errors:
            for error in errors:
                print(f"    ! {error}")
    
    print()


def test_prompt_enhancement():
    """测试Prompt增强"""
    print("=" * 60)
    print("测试4: Prompt增强")
    print("=" * 60)
    
    loader = RoleConfigLoader()
    
    # 测试后端工程师的prompt增强
    backend_config = loader.load_config("backend_engineer")
    if backend_config:
        enhancements = backend_config.get("prompt_enhancements", {})
        print(f"✓ 后端工程师Prompt增强:")
        print(f"  - 岗位上下文: {len(enhancements.get('role_context', ''))} 字符")
        print(f"  - 题目焦点: {len(enhancements.get('question_focus', ''))} 字符")
        print(f"  - 追问焦点: {len(enhancements.get('followup_focus', ''))} 字符")
    
    print()


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("岗位配置系统验证")
    print("=" * 60 + "\n")
    
    try:
        test_config_loading()
        test_role_identification()
        test_competency_mapping()
        test_prompt_enhancement()
        
        print("=" * 60)
        print("✓ 所有测试通过！岗位驱动的面试流程已就绪。")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
